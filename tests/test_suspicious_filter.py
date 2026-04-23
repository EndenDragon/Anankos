import unittest
import datetime
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.suspicious_filter import SuspiciousFilter, _TRACK_WINDOW, _REACTION_SECS


def make_member(age_days, has_avatar=True, flags_value=1, is_bot=False, user_id=1):
    member = MagicMock()
    member.bot = is_bot
    member.id = user_id
    member.name = "testuser"
    member.mention = "<@{}>".format(user_id)
    member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=age_days)
    member.avatar = MagicMock() if has_avatar else None
    member.public_flags.value = flags_value
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


if __name__ == "__main__":
    unittest.main()
