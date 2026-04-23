import unittest
import datetime
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.automod import AutoMod


def make_message(content="hello world", channel_id=1, author_id=100,
                 is_bot=False, has_manage_messages=False, mention_count=0):
    msg = MagicMock()
    msg.content = content
    msg.channel.id = channel_id
    msg.author.id = author_id
    msg.author.bot = is_bot
    msg.guild = MagicMock()
    msg.author.guild_permissions.manage_messages = has_manage_messages
    msg.mentions = [MagicMock() for _ in range(mention_count)]
    msg.author.name = "testuser"
    msg.author.mention = "<@{}>".format(author_id)
    msg.channel.send = AsyncMock()
    msg.author.send = AsyncMock()
    msg.author.ban = AsyncMock()
    return msg


class TestNormalize(unittest.TestCase):
    def setUp(self):
        self.am = AutoMod(MagicMock())

    def test_lowercases_content(self):
        self.assertEqual(self.am._normalize("HELLO WORLD"), "hello world")

    def test_collapses_whitespace(self):
        self.assertEqual(self.am._normalize("hello   world"), "hello world")

    def test_strips_leading_trailing(self):
        self.assertEqual(self.am._normalize("  hello  "), "hello")

    def test_replaces_http_url(self):
        result = self.am._normalize("check http://scam.com/abc out")
        self.assertNotIn("http://scam.com/abc", result)
        self.assertIn("__url__", result)

    def test_replaces_https_url(self):
        result = self.am._normalize("click https://evil.io/x123")
        self.assertIn("__url__", result)

    def test_replaces_www_url(self):
        result = self.am._normalize("visit www.scam.com now")
        self.assertIn("__url__", result)

    def test_different_urls_produce_same_normalized_form(self):
        a = self.am._normalize("click https://scam.com/abc free stuff")
        b = self.am._normalize("click https://scam.com/xyz free stuff")
        self.assertEqual(a, b)


class TestCheckSpam(unittest.TestCase):
    def setUp(self):
        self.am = AutoMod(MagicMock())

    def _pre_populate(self, user_id, content, channel_ids, seconds_ago=5):
        normalized = self.am._normalize(content)
        now = datetime.datetime.now(datetime.timezone.utc)
        for ch_id in channel_ids:
            self.am._recent_messages[user_id].append(
                (ch_id, normalized, now - datetime.timedelta(seconds=seconds_ago))
            )

    def test_no_spam_single_channel(self):
        msg = make_message("buy cheap followers now!!", channel_id=1, author_id=100)
        self.assertIsNone(self.am._check_spam(msg))

    def test_no_spam_two_channels(self):
        content = "buy cheap followers now!!"
        self._pre_populate(100, content, [1])
        msg = make_message(content, channel_id=2, author_id=100)
        self.assertIsNone(self.am._check_spam(msg))

    def test_spam_detected_at_three_channels(self):
        content = "buy cheap followers now!!"
        self._pre_populate(100, content, [1, 2])
        msg = make_message(content, channel_id=3, author_id=100)
        result = self.am._check_spam(msg)
        self.assertIsNotNone(result)
        self.assertIn("3 channels", result)

    def test_spam_reports_correct_channel_count(self):
        content = "spam message here everyone!!"
        self._pre_populate(100, content, [1, 2, 3, 4])
        msg = make_message(content, channel_id=5, author_id=100)
        result = self.am._check_spam(msg)
        self.assertIn("5 channels", result)

    def test_old_messages_outside_window_pruned(self):
        content = "buy cheap followers now!!"
        self._pre_populate(100, content, [1, 2], seconds_ago=60)
        msg = make_message(content, channel_id=3, author_id=100)
        self.assertIsNone(self.am._check_spam(msg))

    def test_different_content_not_spam(self):
        self._pre_populate(100, "first message content here!!", [1, 2])
        msg = make_message("completely unrelated content here", channel_id=3, author_id=100)
        self.assertIsNone(self.am._check_spam(msg))

    def test_content_too_short_not_tracked(self):
        self._pre_populate(100, "hi", [1, 2])
        msg = make_message("hi", channel_id=3, author_id=100)
        self.assertIsNone(self.am._check_spam(msg))

    def test_history_cleared_after_spam_detected(self):
        content = "buy cheap followers now!!"
        self._pre_populate(100, content, [1, 2])
        msg = make_message(content, channel_id=3, author_id=100)
        self.am._check_spam(msg)
        self.assertNotIn(100, self.am._recent_messages)

    def test_independent_users_do_not_interfere(self):
        content = "spam message here everyone!!"
        self._pre_populate(100, content, [1, 2])
        msg = make_message(content, channel_id=3, author_id=200)
        self.assertIsNone(self.am._check_spam(msg))

    def test_url_variants_treated_as_same_content(self):
        content_a = "free nitro at https://scam.com/abc123 claim now"
        content_b = "free nitro at https://scam.com/xyz999 claim now"
        self._pre_populate(100, content_a, [1, 2])
        msg = make_message(content_b, channel_id=3, author_id=100)
        result = self.am._check_spam(msg)
        self.assertIsNotNone(result)


class TestOnMessage(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.am = AutoMod(MagicMock())

    async def test_bot_message_ignored(self):
        msg = make_message(is_bot=True)
        await self.am.on_message(msg)
        msg.author.ban.assert_not_called()

    async def test_dm_message_ignored(self):
        msg = make_message()
        msg.guild = None
        await self.am.on_message(msg)
        msg.author.ban.assert_not_called()

    async def test_manage_messages_bypasses_spam_check(self):
        content = "buy cheap followers now!!"
        normalized = self.am._normalize(content)
        now = datetime.datetime.now(datetime.timezone.utc)
        for ch_id in [1, 2]:
            self.am._recent_messages[100].append(
                (ch_id, normalized, now - datetime.timedelta(seconds=5))
            )
        msg = make_message(content, channel_id=3, author_id=100, has_manage_messages=True)
        await self.am.on_message(msg)
        msg.author.ban.assert_not_called()

    async def test_gift_link_triggers_ban(self):
        msg = make_message("free nitro discord.gift/abc123")
        await self.am.on_message(msg)
        msg.author.ban.assert_called_once()

    async def test_mass_mention_triggers_ban(self):
        msg = make_message("hey everyone", mention_count=7)
        await self.am.on_message(msg)
        msg.author.ban.assert_called_once()

    async def test_spam_across_channels_triggers_ban(self):
        content = "spam message here everyone!!"
        normalized = self.am._normalize(content)
        now = datetime.datetime.now(datetime.timezone.utc)
        for ch_id in [1, 2]:
            self.am._recent_messages[100].append(
                (ch_id, normalized, now - datetime.timedelta(seconds=5))
            )
        msg = make_message(content, channel_id=3, author_id=100)
        await self.am.on_message(msg)
        msg.author.ban.assert_called_once()

    async def test_dm_sent_before_ban(self):
        call_order = []
        msg = make_message("free nitro discord.gift/abc123")
        msg.author.send = AsyncMock(side_effect=lambda *a, **kw: call_order.append("dm"))
        msg.author.ban = AsyncMock(side_effect=lambda *a, **kw: call_order.append("ban"))
        await self.am.on_message(msg)
        self.assertEqual(call_order, ["dm", "ban"])

    async def test_dm_failure_does_not_prevent_ban(self):
        msg = make_message("free nitro discord.gift/abc123")
        msg.author.send = AsyncMock(side_effect=Exception("DM blocked"))
        await self.am.on_message(msg)
        msg.author.ban.assert_called_once()

    async def test_clean_message_no_action(self):
        msg = make_message("hello everyone, how are you doing today?")
        await self.am.on_message(msg)
        msg.author.ban.assert_not_called()


if __name__ == "__main__":
    unittest.main()
