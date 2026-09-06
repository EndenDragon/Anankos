import unittest
import datetime
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.suspicious_filter import SuspiciousFilter, _TRACK_WINDOW, _REACTION_SECS, _MAX_IGNORE_DAYS


def make_member(age_days, has_avatar=True, flags_value=1, is_bot=False, user_id=1, is_spammer=False):
    member = MagicMock()
    member.bot = is_bot
    member.id = user_id
    member.name = "testuser"
    member.mention = "<@{}>".format(user_id)
    member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=age_days)
    member.avatar = MagicMock() if has_avatar else None
    member.public_flags.value = flags_value
    member.public_flags.spammer = is_spammer
    member.joined_at = datetime.datetime.now(datetime.timezone.utc)
    member.send = AsyncMock()
    member.kick = AsyncMock()
    return member


def make_payload(user_id, channel_id, guild_id=500):
    payload = MagicMock()
    payload.user_id = user_id
    payload.channel_id = channel_id
    payload.guild_id = guild_id
    return payload


class TestScore(unittest.TestCase):
    def setUp(self):
        self.sf = SuspiciousFilter(MagicMock(), log_channelid=None, welcome_channelids=[])

    def test_account_under_7_days_scores_50(self):
        score, _ = self.sf._score(make_member(age_days=3))
        self.assertEqual(score, 50)

    def test_account_7_to_30_days_scores_30(self):
        score, _ = self.sf._score(make_member(age_days=10))
        self.assertEqual(score, 30)

    def test_account_30_to_60_days_scores_15(self):
        score, _ = self.sf._score(make_member(age_days=45))
        self.assertEqual(score, 15)

    def test_account_over_60_days_scores_0_for_age(self):
        score, _ = self.sf._score(make_member(age_days=365))
        self.assertEqual(score, 0)

    def test_no_avatar_adds_20(self):
        score, _ = self.sf._score(make_member(age_days=365, has_avatar=False))
        self.assertEqual(score, 20)

    def test_has_avatar_adds_0(self):
        score, _ = self.sf._score(make_member(age_days=365, has_avatar=True))
        self.assertEqual(score, 0)

    def test_no_flags_adds_10(self):
        score, _ = self.sf._score(make_member(age_days=365, flags_value=0))
        self.assertEqual(score, 10)

    def test_has_flags_adds_0(self):
        score, _ = self.sf._score(make_member(age_days=365, flags_value=1))
        self.assertEqual(score, 0)

    def test_multiple_signals_combine(self):
        # 10 days (30) + no avatar (20) + no flags (10) = 60
        member = make_member(age_days=10, has_avatar=False, flags_value=0)
        score, _ = self.sf._score(member)
        self.assertEqual(score, 60)

    def test_discord_spammer_flag_scores_100_and_short_circuits(self):
        member = make_member(age_days=365, has_avatar=True, flags_value=1, is_spammer=True)
        score, breakdown = self.sf._score(member)
        self.assertEqual(score, 100)
        self.assertEqual(len(breakdown), 1)
        self.assertIn("spammer", breakdown[0][0].lower())

    def test_breakdown_labels_present(self):
        member = make_member(age_days=3, has_avatar=False)
        _, breakdown = self.sf._score(member)
        labels = [label for label, _ in breakdown]
        self.assertTrue(any("day" in l for l in labels))
        self.assertTrue(any("profile picture" in l for l in labels))


class TestFormatBreakdown(unittest.TestCase):
    def setUp(self):
        self.sf = SuspiciousFilter(MagicMock(), log_channelid=None, welcome_channelids=[])

    def test_shows_score_and_threshold(self):
        result = self.sf._format_breakdown([("account only 3 day(s) old", 50)], 50, 40)
        self.assertIn("50/40", result)

    def test_shows_each_signal_with_points(self):
        breakdown = [("account only 3 day(s) old", 50), ("no profile picture", 20)]
        result = self.sf._format_breakdown(breakdown, 70, 40)
        self.assertIn("account only 3 day(s) old (+50)", result)
        self.assertIn("no profile picture (+20)", result)


class TestOnMemberJoin(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.get_channel.return_value = None
        self.sf = SuspiciousFilter(self.client, log_channelid=None, welcome_channelids=[], kick_score=40)

    async def test_bot_skipped_returns_false(self):
        result = await self.sf.on_member_join(make_member(age_days=1, is_bot=True))
        self.assertFalse(result)

    async def test_bot_not_kicked(self):
        member = make_member(age_days=1, is_bot=True)
        await self.sf.on_member_join(member)
        member.kick.assert_not_called()

    async def test_high_score_kicks_and_returns_true(self):
        member = make_member(age_days=3)  # score=50
        result = await self.sf.on_member_join(member)
        self.assertTrue(result)
        member.kick.assert_called_once()

    async def test_score_below_threshold_no_kick_returns_false(self):
        member = make_member(age_days=365, has_avatar=True, flags_value=1)  # score=0
        result = await self.sf.on_member_join(member)
        self.assertFalse(result)
        member.kick.assert_not_called()

    async def test_dm_sent_before_kick(self):
        call_order = []
        member = make_member(age_days=3)
        member.send = AsyncMock(side_effect=lambda *a, **kw: call_order.append("dm"))
        member.kick = AsyncMock(side_effect=lambda *a, **kw: call_order.append("kick"))
        await self.sf.on_member_join(member)
        self.assertEqual(call_order, ["dm", "kick"])

    async def test_dm_failure_does_not_prevent_kick(self):
        member = make_member(age_days=3)
        member.send = AsyncMock(side_effect=Exception("DM blocked"))
        await self.sf.on_member_join(member)
        member.kick.assert_called_once()

    async def test_tracked_member_added_to_recently_joined(self):
        member = make_member(age_days=365, user_id=42)  # score=0, below threshold
        await self.sf.on_member_join(member)
        self.assertIn(42, self.sf._recently_joined)

    async def test_kicked_member_not_added_to_recently_joined(self):
        member = make_member(age_days=3, user_id=42)  # score=50, above threshold
        await self.sf.on_member_join(member)
        self.assertNotIn(42, self.sf._recently_joined)

    async def test_log_channel_receives_breakdown_with_score(self):
        log_channel = MagicMock()
        log_channel.send = AsyncMock()
        self.client.get_channel.return_value = log_channel
        self.sf.log_channelid = 999

        member = make_member(age_days=3)  # score=50
        await self.sf.on_member_join(member)

        log_channel.send.assert_called_once()
        log_text = log_channel.send.call_args[0][0]
        self.assertIn("50/40", log_text)

    async def test_log_channel_includes_username(self):
        log_channel = MagicMock()
        log_channel.send = AsyncMock()
        self.client.get_channel.return_value = log_channel
        self.sf.log_channelid = 999

        member = make_member(age_days=3)
        member.name = "spambot9000"
        await self.sf.on_member_join(member)

        log_text = log_channel.send.call_args[0][0]
        self.assertIn("spambot9000", log_text)


class TestOnRawReactionAdd(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.get_channel.return_value = None
        self.sf = SuspiciousFilter(
            self.client,
            log_channelid=None,
            welcome_channelids=[200],
            kick_score=40,
        )

    def _track(self, user_id, seconds_ago=10):
        self.sf._recently_joined[user_id] = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds_ago)
        )

    def _setup_guild(self, member):
        guild = MagicMock()
        guild.get_member.return_value = member
        self.client.get_guild.return_value = guild

    async def test_wrong_channel_ignored(self):
        self._track(1)
        await self.sf.on_raw_reaction_add(make_payload(user_id=1, channel_id=999))
        self.client.get_guild.assert_not_called()

    async def test_user_not_in_recently_joined_ignored(self):
        await self.sf.on_raw_reaction_add(make_payload(user_id=1, channel_id=200))
        self.client.get_guild.assert_not_called()

    async def test_reaction_tips_borderline_member_over_threshold(self):
        # 45 days (15) + no avatar (20) = 35 base < 40 → tracked
        # 35 + reaction (25) = 60 >= 40 → kick
        member = make_member(age_days=45, has_avatar=False, flags_value=1, user_id=1)
        self._setup_guild(member)
        self._track(member.id, seconds_ago=10)
        await self.sf.on_raw_reaction_add(make_payload(user_id=member.id, channel_id=200))
        member.kick.assert_called_once()

    async def test_safe_member_reacts_quickly_not_kicked(self):
        # 365 days (0) + avatar (0) + flags (0) = 0 base
        # 0 + reaction (25) = 25 < 40 → no kick
        member = make_member(age_days=365, has_avatar=True, flags_value=1, user_id=1)
        self._setup_guild(member)
        self._track(member.id, seconds_ago=10)
        await self.sf.on_raw_reaction_add(make_payload(user_id=member.id, channel_id=200))
        member.kick.assert_not_called()

    async def test_reaction_after_reaction_threshold_ignored(self):
        member = make_member(age_days=45, has_avatar=False, flags_value=1, user_id=1)
        self._setup_guild(member)
        self._track(member.id, seconds_ago=_REACTION_SECS + 30)
        await self.sf.on_raw_reaction_add(make_payload(user_id=member.id, channel_id=200))
        member.kick.assert_not_called()

    async def test_kicked_member_removed_from_recently_joined(self):
        member = make_member(age_days=45, has_avatar=False, flags_value=1, user_id=1)
        self._setup_guild(member)
        self._track(member.id, seconds_ago=10)
        await self.sf.on_raw_reaction_add(make_payload(user_id=member.id, channel_id=200))
        self.assertNotIn(member.id, self.sf._recently_joined)

    async def test_stale_entries_pruned(self):
        stale_id = 99
        self.sf._recently_joined[stale_id] = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=_TRACK_WINDOW + 60)
        )
        # A different user reacts → triggers pruning
        member = make_member(age_days=365, user_id=1, flags_value=1)
        self._setup_guild(member)
        self._track(member.id, seconds_ago=10)
        await self.sf.on_raw_reaction_add(make_payload(user_id=member.id, channel_id=200))
        self.assertNotIn(stale_id, self.sf._recently_joined)

    async def test_bot_member_not_kicked(self):
        member = make_member(age_days=3, is_bot=True, user_id=1)
        self._setup_guild(member)
        self._track(member.id, seconds_ago=10)
        await self.sf.on_raw_reaction_add(make_payload(user_id=member.id, channel_id=200))
        member.kick.assert_not_called()


def make_message(content, user_id=7, can_manage=True):
    message = MagicMock()
    message.author.id = user_id
    message.author.mention = "<@{}>".format(user_id)
    message.content = content
    message.channel.permissions_for.return_value.manage_guild = can_manage
    message.channel.send = AsyncMock()
    return message


class TestIgnoreList(unittest.TestCase):
    def setUp(self):
        self.sf = SuspiciousFilter(MagicMock(), log_channelid=None, welcome_channelids=[])

    def test_add_ignore_lowercases_and_strips_at(self):
        name, _, is_id = self.sf.add_ignore("@SpamBot9000")
        self.assertEqual(name, "spambot9000")
        self.assertFalse(is_id)

    def test_add_ignore_defaults_to_max_days(self):
        _, expiry, _ = self.sf.add_ignore("someone")
        delta = expiry - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(delta.total_seconds(), _MAX_IGNORE_DAYS * 86400, delta=5)

    def test_add_ignore_caps_at_max_days(self):
        _, expiry, _ = self.sf.add_ignore("someone", days=30)
        delta = expiry - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(delta.total_seconds(), _MAX_IGNORE_DAYS * 86400, delta=5)

    def test_add_ignore_accepts_shorter_duration(self):
        _, expiry, _ = self.sf.add_ignore("someone", days=1)
        delta = expiry - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(delta.total_seconds(), 86400, delta=5)

    def test_add_ignore_rejects_empty_username(self):
        self.assertIsNone(self.sf.add_ignore("   "))

    def test_add_ignore_rejects_zero_or_negative_days(self):
        self.assertIsNone(self.sf.add_ignore("someone", days=0))
        self.assertIsNone(self.sf.add_ignore("someone", days=-3))

    def test_is_ignored_matches_username(self):
        self.sf.add_ignore("TestUser")
        self.assertTrue(self.sf.is_ignored(make_member(age_days=1)))

    def test_is_ignored_matches_global_name(self):
        member = make_member(age_days=1)
        member.name = "someone_else"
        member.global_name = "TestUser"
        self.sf.add_ignore("testuser")
        self.assertTrue(self.sf.is_ignored(member))

    def test_is_ignored_false_for_unlisted_user(self):
        self.assertFalse(self.sf.is_ignored(make_member(age_days=1)))

    def test_expired_entry_no_longer_ignored(self):
        self.sf._ignored["testuser"] = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        )
        self.assertFalse(self.sf.is_ignored(make_member(age_days=1)))
        self.assertNotIn("testuser", self.sf._ignored)

    def test_remove_ignore_clears_entry(self):
        self.sf.add_ignore("TestUser")
        self.assertEqual(self.sf.remove_ignore("@TESTUSER"), ("testuser", False))
        self.assertFalse(self.sf.is_ignored(make_member(age_days=1)))

    def test_remove_ignore_returns_none_when_absent(self):
        self.assertIsNone(self.sf.remove_ignore("nobody"))

    def test_list_ignored_sorted_by_expiry(self):
        self.sf.add_ignore("later", days=4)
        self.sf.add_ignore("sooner", days=1)
        self.assertEqual([name for name, _, _ in self.sf.list_ignored()], ["sooner", "later"])

    def test_list_ignored_excludes_expired(self):
        self.sf.add_ignore("live")
        self.sf._ignored["dead"] = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        self.assertEqual([name for name, _, _ in self.sf.list_ignored()], ["live"])

    def test_add_ignore_username_case_insensitive_dedupes(self):
        self.sf.add_ignore("TestUser")
        self.sf.add_ignore("TESTUSER")
        self.assertEqual(len(self.sf._ignored), 1)

    def test_add_ignore_long_digit_string_treated_as_id(self):
        key, _, is_id = self.sf.add_ignore("123456789012345678")
        self.assertEqual(key, "123456789012345678")
        self.assertTrue(is_id)

    def test_add_ignore_short_digit_string_treated_as_username(self):
        key, _, is_id = self.sf.add_ignore("12345")
        self.assertEqual(key, "12345")
        self.assertFalse(is_id)

    def test_add_ignore_mention_format_treated_as_id(self):
        key, _, is_id = self.sf.add_ignore("<@123456789012345678>")
        self.assertEqual(key, "123456789012345678")
        self.assertTrue(is_id)

    def test_add_ignore_nickname_mention_format_treated_as_id(self):
        key, _, is_id = self.sf.add_ignore("<@!123456789012345678>")
        self.assertEqual(key, "123456789012345678")
        self.assertTrue(is_id)

    def test_is_ignored_matches_user_id(self):
        member = make_member(age_days=1, user_id=123456789012345678)
        self.sf.add_ignore("123456789012345678")
        self.assertTrue(self.sf.is_ignored(member))

    def test_is_ignored_id_does_not_match_wrong_user(self):
        member = make_member(age_days=1, user_id=1)
        self.sf.add_ignore("123456789012345678")
        self.assertFalse(self.sf.is_ignored(member))

    def test_remove_ignore_by_id(self):
        self.sf.add_ignore("123456789012345678")
        self.assertEqual(self.sf.remove_ignore("123456789012345678"), ("123456789012345678", True))

    def test_remove_ignore_by_mention(self):
        self.sf.add_ignore("123456789012345678")
        self.assertEqual(self.sf.remove_ignore("<@123456789012345678>"), ("123456789012345678", True))

    def test_list_ignored_flags_id_entries(self):
        self.sf.add_ignore("123456789012345678")
        self.sf.add_ignore("someone")
        flags = {key: is_id for key, _, is_id in self.sf.list_ignored()}
        self.assertTrue(flags["123456789012345678"])
        self.assertFalse(flags["someone"])


class TestIgnoreSkipsFilter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.get_channel.return_value = None
        self.sf = SuspiciousFilter(self.client, log_channelid=None, welcome_channelids=[200], kick_score=40)

    async def test_ignored_member_not_kicked_on_join(self):
        member = make_member(age_days=1, has_avatar=False, flags_value=0)  # score=80
        self.sf.add_ignore(member.name)
        result = await self.sf.on_member_join(member)
        self.assertFalse(result)
        member.kick.assert_not_called()

    async def test_ignored_member_not_tracked_on_join(self):
        member = make_member(age_days=1, user_id=42)
        self.sf.add_ignore(member.name)
        await self.sf.on_member_join(member)
        self.assertNotIn(42, self.sf._recently_joined)

    async def test_ignored_member_not_kicked_on_reaction(self):
        member = make_member(age_days=45, has_avatar=False, flags_value=1, user_id=1)
        guild = MagicMock()
        guild.get_member.return_value = member
        self.client.get_guild.return_value = guild
        self.sf._recently_joined[member.id] = datetime.datetime.now(datetime.timezone.utc)
        self.sf.add_ignore(member.name)
        await self.sf.on_raw_reaction_add(make_payload(user_id=member.id, channel_id=200))
        member.kick.assert_not_called()

    async def test_expired_ignore_no_longer_protects(self):
        member = make_member(age_days=1)
        self.sf._ignored[member.name] = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        )
        result = await self.sf.on_member_join(member)
        self.assertTrue(result)
        member.kick.assert_called_once()

    async def test_ignored_by_id_not_kicked_on_join(self):
        member = make_member(age_days=1, has_avatar=False, flags_value=0, user_id=123456789012345678)
        self.sf.add_ignore(str(member.id))
        result = await self.sf.on_member_join(member)
        self.assertFalse(result)
        member.kick.assert_not_called()


class TestIgnoreCommands(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.user.id = 999
        self.client.cmd_prefix = "!"
        self.sf = SuspiciousFilter(self.client, log_channelid=None, welcome_channelids=[])

    async def test_susignore_adds_username(self):
        await self.sf.on_message(make_message("!susignore SpamBot9000"))
        self.assertIn("spambot9000", self.sf._ignored)

    async def test_susignore_with_days(self):
        await self.sf.on_message(make_message("!susignore someone 2"))
        delta = self.sf._ignored["someone"] - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(delta.total_seconds(), 2 * 86400, delta=5)

    async def test_susignore_caps_days_at_max(self):
        await self.sf.on_message(make_message("!susignore someone 99"))
        delta = self.sf._ignored["someone"] - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(delta.total_seconds(), _MAX_IGNORE_DAYS * 86400, delta=5)

    async def test_susignore_multiword_non_numeric_trailer_treated_as_username(self):
        # "word" isn't a valid day count, so the whole phrase is the username at default duration
        await self.sf.on_message(make_message("!susignore multi word"))
        self.assertIn("multi word", self.sf._ignored)
        delta = self.sf._ignored["multi word"] - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(delta.total_seconds(), _MAX_IGNORE_DAYS * 86400, delta=5)

    async def test_susignore_reports_invalid_username(self):
        message = make_message("!susignore @")
        await self.sf.on_message(message)
        self.assertEqual(self.sf._ignored, {})
        self.assertIn("Invalid username, user ID, or duration", message.channel.send.call_args[0][0])

    async def test_susignore_adds_user_id(self):
        message = make_message("!susignore 123456789012345678")
        await self.sf.on_message(message)
        self.assertIn("123456789012345678", self.sf._ignored)
        reply = message.channel.send.call_args[0][0]
        self.assertIn("123456789012345678", reply)
        self.assertNotIn("<@123456789012345678>", reply)

    async def test_susignore_adds_mention(self):
        await self.sf.on_message(make_message("!susignore <@123456789012345678>"))
        self.assertIn("123456789012345678", self.sf._ignored)

    async def test_susignore_id_with_days(self):
        await self.sf.on_message(make_message("!susignore 123456789012345678 2"))
        delta = self.sf._ignored["123456789012345678"] - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(delta.total_seconds(), 2 * 86400, delta=5)

    async def test_susignore_without_args_shows_usage(self):
        message = make_message("!susignore")
        await self.sf.on_message(message)
        self.assertEqual(self.sf._ignored, {})
        self.assertIn("Usage", message.channel.send.call_args[0][0])

    async def test_susignore_requires_manage_guild(self):
        message = make_message("!susignore someone", can_manage=False)
        await self.sf.on_message(message)
        self.assertEqual(self.sf._ignored, {})
        message.channel.send.assert_not_called()

    async def test_susunignore_without_args_shows_usage(self):
        message = make_message("!susunignore")
        await self.sf.on_message(message)
        self.assertIn("Usage", message.channel.send.call_args[0][0])

    async def test_susunignore_removes_username(self):
        self.sf.add_ignore("someone")
        await self.sf.on_message(make_message("!susunignore someone"))
        self.assertNotIn("someone", self.sf._ignored)

    async def test_susunignore_reports_when_absent(self):
        message = make_message("!susunignore nobody")
        await self.sf.on_message(message)
        self.assertIn("not on the suspicious filter ignore list", message.channel.send.call_args[0][0])

    async def test_susunignore_requires_manage_guild(self):
        self.sf.add_ignore("someone")
        await self.sf.on_message(make_message("!susunignore someone", can_manage=False))
        self.assertIn("someone", self.sf._ignored)

    async def test_susunignore_removes_by_id(self):
        self.sf.add_ignore("123456789012345678")
        message = make_message("!susunignore 123456789012345678")
        await self.sf.on_message(message)
        self.assertNotIn("123456789012345678", self.sf._ignored)
        reply = message.channel.send.call_args[0][0]
        self.assertIn("123456789012345678", reply)
        self.assertNotIn("<@123456789012345678>", reply)

    async def test_susunignore_removes_by_mention(self):
        self.sf.add_ignore("123456789012345678")
        await self.sf.on_message(make_message("!susunignore <@123456789012345678>"))
        self.assertNotIn("123456789012345678", self.sf._ignored)

    async def test_suslistignore_lists_entries(self):
        self.sf.add_ignore("alpha")
        self.sf.add_ignore("beta")
        message = make_message("!suslistignore")
        await self.sf.on_message(message)
        text = message.channel.send.call_args[0][0]
        self.assertIn("alpha", text)
        self.assertIn("beta", text)

    async def test_suslistignore_when_empty(self):
        message = make_message("!suslistignore")
        await self.sf.on_message(message)
        self.assertIn("No usernames", message.channel.send.call_args[0][0])

    async def test_suslistignore_shows_id_without_pinging(self):
        self.sf.add_ignore("123456789012345678")
        message = make_message("!suslistignore")
        await self.sf.on_message(message)
        reply = message.channel.send.call_args[0][0]
        self.assertIn("123456789012345678", reply)
        self.assertNotIn("<@123456789012345678>", reply)

    async def test_suslistignore_requires_manage_guild(self):
        message = make_message("!suslistignore", can_manage=False)
        await self.sf.on_message(message)
        message.channel.send.assert_not_called()

    async def test_susunignore_not_swallowed_by_susignore_prefix(self):
        self.sf.add_ignore("someone")
        await self.sf.on_message(make_message("!susunignore someone"))
        self.assertEqual(self.sf._ignored, {})

    async def test_own_messages_ignored(self):
        message = make_message("!susignore someone", user_id=999)
        await self.sf.on_message(message)
        self.assertEqual(self.sf._ignored, {})

    async def test_unrelated_message_ignored(self):
        message = make_message("just chatting")
        await self.sf.on_message(message)
        message.channel.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
