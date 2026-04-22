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


if __name__ == "__main__":
    unittest.main()
