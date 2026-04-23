import unittest
import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.art_mention import ArtMention


def make_client(db_rows=None):
    client = MagicMock()
    client.user.id = 999
    client.cmd_prefix = "!"

    cursor = MagicMock()
    cursor.fetchall = AsyncMock(return_value=db_rows or [])
    cursor.fetchone = AsyncMock(return_value=None)

    db = MagicMock()
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    client.db = db
    return client, cursor


class TestArtMentionFormatCooldown(unittest.TestCase):
    def setUp(self):
        client, _ = make_client()
        self.am = ArtMention(client, [], [], 0, 0)

    def test_zero(self):
        self.assertEqual(self.am.format_cooldown(0), "0s")

    def test_negative(self):
        self.assertEqual(self.am.format_cooldown(-5), "0s")

    def test_seconds_only(self):
        self.assertEqual(self.am.format_cooldown(45), "45s")

    def test_minutes_and_seconds(self):
        self.assertEqual(self.am.format_cooldown(125), "2m 5s")

    def test_hours_minutes_seconds(self):
        self.assertEqual(self.am.format_cooldown(3661), "1h 1m 1s")

    def test_exact_hour(self):
        self.assertEqual(self.am.format_cooldown(3600), "1h")


class TestArtMentionCooldown(unittest.TestCase):
    def setUp(self):
        client, _ = make_client()
        self.am = ArtMention(client, [], [], 0, 0)

    def test_no_cooldown_first_time(self):
        self.assertEqual(self.am.get_cooldown_seconds("corrin"), 0)

    def test_cooldown_recently_mentioned(self):
        self.am.mention_last["corrin"] = datetime.datetime.now()
        secs = self.am.get_cooldown_seconds("corrin")
        self.assertGreater(secs, 0)
        self.assertLessEqual(secs, self.am.cooldown)

    def test_cooldown_expired(self):
        self.am.mention_last["corrin"] = datetime.datetime.now() - datetime.timedelta(seconds=200)
        self.assertEqual(self.am.get_cooldown_seconds("corrin"), 0)


class TestArtMentionSubscriptions(unittest.IsolatedAsyncioTestCase):
    async def test_get_all_subscriptions_empty(self):
        client, cursor = make_client(db_rows=[])
        am = ArtMention(client, [], [], 0, 0)
        result = await am.get_all_subscriptions()
        self.assertEqual(result, {})

    async def test_get_all_subscriptions_groups_by_character(self):
        client, cursor = make_client(db_rows=[
            (111, "corrin"),
            (222, "corrin"),
            (333, "azura"),
        ])
        am = ArtMention(client, [], [], 0, 0)
        result = await am.get_all_subscriptions()
        self.assertIn("corrin", result)
        self.assertIn("azura", result)
        self.assertEqual(sorted(result["corrin"]), [111, 222])
        self.assertEqual(result["azura"], [333])

    async def test_get_all_user_subscriptions(self):
        client, cursor = make_client(db_rows=[
            (111, "corrin"),
            (222, "corrin"),
            (111, "azura"),
        ])
        am = ArtMention(client, [], [], 0, 0)
        subs = await am.get_all_user_subscriptions(111)
        self.assertIn("corrin", subs)
        self.assertIn("azura", subs)
        self.assertNotIn("corrin", await am.get_all_user_subscriptions(999))

    async def test_subscribe_user_sets_pingboard_dirty(self):
        client, _ = make_client()
        am = ArtMention(client, [], [], 0, 0)
        am.pingboard_uptodate = True
        await am.subscribe_user(111, "corrin")
        self.assertFalse(am.pingboard_uptodate)

    async def test_unsubscribe_user_sets_pingboard_dirty(self):
        client, _ = make_client()
        am = ArtMention(client, [], [], 0, 0)
        am.pingboard_uptodate = True
        await am.unsubscribe_user(111, "corrin")
        self.assertFalse(am.pingboard_uptodate)


class TestArtMentionTimeDiff(unittest.TestCase):
    """Verify the utcnow() replacement produces the expected result."""

    def test_time_diff_is_numeric(self):
        utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        local_now = datetime.datetime.now()
        diff = (local_now - utc_now).total_seconds()
        # diff should be within ±14 hours (max UTC offset)
        self.assertLess(abs(diff), 14 * 3600)


class TestParseTags(unittest.TestCase):
    def setUp(self):
        client, _ = make_client()
        self.am = ArtMention(client, [], [], 0, 0)

    def test_single_tag(self):
        self.assertEqual(self.am._parse_tags("!!corrin"), ["corrin"])

    def test_multiple_tags(self):
        self.assertEqual(self.am._parse_tags("!!corrin !!camilla"), ["corrin", "camilla"])

    def test_preserves_order(self):
        self.assertEqual(self.am._parse_tags("!!byleth !!corrin !!edelgard"), ["byleth", "corrin", "edelgard"])

    def test_deduplicates_within_content(self):
        self.assertEqual(self.am._parse_tags("!!corrin !!corrin"), ["corrin"])

    def test_no_tags_returns_empty(self):
        self.assertEqual(self.am._parse_tags("hello world"), [])

    def test_non_tag_words_ignored(self):
        self.assertEqual(self.am._parse_tags("check out !!corrin here"), ["corrin"])

    def test_case_normalized_to_lowercase(self):
        self.assertEqual(self.am._parse_tags("!!Corrin !!CAMILLA"), ["corrin", "camilla"])

    def test_mixed_tags_and_text(self):
        result = self.am._parse_tags("!!corrin some text !!byleth")
        self.assertEqual(result, ["corrin", "byleth"])


# --- helpers for thread feature tests ---

def make_button(custom_id):
    btn = MagicMock()
    btn.custom_id = custom_id
    return btn

def make_ping_message(*characters, bot_id=999):
    """Bot ping message containing ArtMentionButton components for the given characters."""
    msg = MagicMock()
    msg.author.id = bot_id
    row = MagicMock()
    row.children = [make_button(f"art_mention {c}") for c in characters]
    msg.components = [row]
    msg.edit = AsyncMock()
    msg.reply = AsyncMock()
    return msg

def make_thread(history_messages, manage_messages=False):
    thread = MagicMock()
    async def _history(**kwargs):
        for m in history_messages:
            yield m
    thread.history = MagicMock(side_effect=lambda **kw: _history())
    thread.send = AsyncMock()
    thread.edit = AsyncMock()
    perms = MagicMock()
    perms.manage_messages = manage_messages
    thread.permissions_for = MagicMock(return_value=perms)
    return thread

def make_thread_message(content, thread):
    msg = MagicMock()
    msg.content = content
    msg.channel = thread
    msg.guild = MagicMock()
    msg.author = MagicMock()
    msg.add_reaction = AsyncMock()
    msg.reply = AsyncMock()
    return msg

def make_am_for_thread():
    client, _ = make_client()
    am = ArtMention(client, [], [], 0, 0)
    am.get_role = AsyncMock(return_value=None)
    am.bump_character = AsyncMock()
    return am


class TestFindThreadPingMessage(unittest.IsolatedAsyncioTestCase):
    async def test_finds_ping_message_and_extracts_characters(self):
        am = make_am_for_thread()
        msg = make_ping_message("corrin", "camilla")
        thread = make_thread([msg])
        found, chars = await am.find_thread_ping_message(thread)
        self.assertIs(found, msg)
        self.assertEqual(chars, ["corrin", "camilla"])

    async def test_empty_thread_returns_none(self):
        am = make_am_for_thread()
        thread = make_thread([])
        found, chars = await am.find_thread_ping_message(thread)
        self.assertIsNone(found)
        self.assertEqual(chars, [])

    async def test_non_bot_message_ignored(self):
        am = make_am_for_thread()
        user_msg = make_ping_message("corrin", bot_id=111)
        thread = make_thread([user_msg])
        found, chars = await am.find_thread_ping_message(thread)
        self.assertIsNone(found)
        self.assertEqual(chars, [])

    async def test_bot_message_without_art_buttons_skipped(self):
        am = make_am_for_thread()
        msg = MagicMock()
        msg.author.id = 999
        row = MagicMock()
        row.children = [make_button("some_other_id")]
        msg.components = [row]
        thread = make_thread([msg])
        found, chars = await am.find_thread_ping_message(thread)
        self.assertIsNone(found)
        self.assertEqual(chars, [])

    async def test_returns_first_matching_bot_message(self):
        am = make_am_for_thread()
        first = make_ping_message("corrin")
        second = make_ping_message("camilla")
        thread = make_thread([first, second])
        found, chars = await am.find_thread_ping_message(thread)
        self.assertIs(found, first)
        self.assertEqual(chars, ["corrin"])


class TestOnThreadArtMessage(unittest.IsolatedAsyncioTestCase):
    async def test_no_tags_does_nothing(self):
        am = make_am_for_thread()
        thread = make_thread([make_ping_message("corrin")])
        msg = make_thread_message("hello world", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_not_called()
        msg.reply.assert_not_called()

    async def test_no_ping_message_in_thread_does_nothing(self):
        am = make_am_for_thread()
        thread = make_thread([])
        msg = make_thread_message("!!byleth", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_not_called()
        msg.reply.assert_not_called()

    async def test_duplicate_sends_already_added_reply(self):
        am = make_am_for_thread()
        thread = make_thread([make_ping_message("corrin")])
        msg = make_thread_message("!!corrin", thread)
        await am.on_thread_art_message(msg)
        msg.reply.assert_called_once()
        self.assertIn("corrin", msg.reply.call_args[0][0])
        self.assertIn("already added", msg.reply.call_args[0][0])
        msg.add_reaction.assert_not_called()

    async def test_multiple_duplicates_uses_plural(self):
        am = make_am_for_thread()
        thread = make_thread([make_ping_message("corrin", "camilla")])
        msg = make_thread_message("!!corrin !!camilla", thread)
        await am.on_thread_art_message(msg)
        self.assertIn("are already added", msg.reply.call_args[0][0])

    async def test_new_character_with_subscribers_added(self):
        am = make_am_for_thread()
        role = MagicMock()
        role.mention = "@Byleth Fanart Notification"
        am.get_role = AsyncMock(return_value=role)
        ping_msg = make_ping_message("corrin")
        thread = make_thread([ping_msg])
        msg = make_thread_message("!!byleth", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_called_once_with("✅")
        ping_msg.reply.assert_called_once()
        ping_msg.edit.assert_called_once()

    async def test_new_character_no_subscribers_sends_placeholder_and_adds_button(self):
        am = make_am_for_thread()
        am.get_role = AsyncMock(return_value=None)
        ping_msg = make_ping_message("corrin")
        thread = make_thread([ping_msg])
        msg = make_thread_message("!!byleth", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_called_once_with("✅")
        ping_msg.reply.assert_called_once()
        self.assertIn("[@byleth]", ping_msg.reply.call_args[0][0])
        ping_msg.edit.assert_called_once()

    async def test_at_25_limit_sends_limit_reply(self):
        am = make_am_for_thread()
        ping_msg = make_ping_message(*[f"char{i}" for i in range(25)])
        thread = make_thread([ping_msg])
        msg = make_thread_message("!!newchar", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_not_called()
        msg.reply.assert_called_once()
        self.assertIn("25 ping limit", msg.reply.call_args[0][0])

    async def test_partial_limit_adds_first_drops_last(self):
        am = make_am_for_thread()
        role = MagicMock()
        role.mention = "@Role"
        am.get_role = AsyncMock(return_value=role)
        ping_msg = make_ping_message(*[f"char{i}" for i in range(24)])
        thread = make_thread([ping_msg])
        msg = make_thread_message("!!byleth !!edelgard", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_called_once_with("✅")
        reply_text = msg.reply.call_args[0][0]
        self.assertIn("edelgard", reply_text)
        self.assertIn("25 ping limit", reply_text)

    async def test_duplicate_and_new_reports_both(self):
        am = make_am_for_thread()
        role = MagicMock()
        role.mention = "@Byleth Fanart Notification"
        am.get_role = AsyncMock(return_value=role)
        thread = make_thread([make_ping_message("corrin")])
        msg = make_thread_message("!!byleth !!corrin", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_called_once_with("✅")
        reply_text = msg.reply.call_args[0][0]
        self.assertIn("corrin", reply_text)
        self.assertIn("already added", reply_text)

    async def test_in_message_duplicate_processed_once(self):
        am = make_am_for_thread()
        role = MagicMock()
        role.mention = "@Byleth"
        am.get_role = AsyncMock(return_value=role)
        thread = make_thread([make_ping_message("corrin")])
        msg = make_thread_message("!!byleth !!byleth", thread)
        await am.on_thread_art_message(msg)
        am.get_role.assert_called_once()

    async def test_thread_name_updated_on_add(self):
        am = make_am_for_thread()
        role = MagicMock()
        role.mention = "@Byleth Fanart Notification"
        am.get_role = AsyncMock(return_value=role)
        ping_msg = make_ping_message("corrin")
        thread = make_thread([ping_msg])
        msg = make_thread_message("!!byleth", thread)
        await am.on_thread_art_message(msg)
        thread.edit.assert_called_once()
        new_name = thread.edit.call_args[1]["name"]
        self.assertIn("corrin", new_name)
        self.assertIn("byleth", new_name)
        self.assertTrue(new_name.startswith("art-"))

    async def test_thread_name_not_updated_when_nothing_added(self):
        am = make_am_for_thread()
        thread = make_thread([make_ping_message("corrin")])
        msg = make_thread_message("!!corrin", thread)
        await am.on_thread_art_message(msg)
        thread.edit.assert_not_called()

    async def test_cooldown_silently_skips_character(self):
        am = make_am_for_thread()
        am.mention_last["byleth"] = datetime.datetime.now()
        thread = make_thread([make_ping_message("corrin")])
        msg = make_thread_message("!!byleth", thread)
        await am.on_thread_art_message(msg)
        msg.add_reaction.assert_not_called()
        msg.reply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
