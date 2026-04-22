import unittest
import datetime
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.pick_a_number import PickANumber


def make_pan():
    client = MagicMock()
    client.user.id = 999
    client.cmd_prefix = "!"
    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor.fetchall = AsyncMock(return_value=[])
    db = MagicMock()
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    client.db = db
    return PickANumber(client, enabled=True, channel_id=100, event_id="test", cooldown=60)


class TestPickANumberIsInt(unittest.TestCase):
    def setUp(self):
        self.pan = make_pan()

    def test_valid_int(self):
        self.assertTrue(self.pan.is_int("42"))

    def test_negative_int(self):
        self.assertTrue(self.pan.is_int("-5"))

    def test_float_string(self):
        self.assertFalse(self.pan.is_int("3.14"))

    def test_word(self):
        self.assertFalse(self.pan.is_int("hello"))

    def test_empty(self):
        self.assertFalse(self.pan.is_int(""))


class TestPickANumberFormatCooldown(unittest.TestCase):
    def setUp(self):
        self.pan = make_pan()

    def test_zero(self):
        self.assertEqual(self.pan.format_cooldown(0), "0s")

    def test_seconds_only(self):
        self.assertEqual(self.pan.format_cooldown(30), "30s")

    def test_minutes_and_seconds(self):
        self.assertEqual(self.pan.format_cooldown(90), "1m 30s")

    def test_hours_only(self):
        self.assertEqual(self.pan.format_cooldown(7200), "2h")


class TestPickANumberCooldownSeconds(unittest.IsolatedAsyncioTestCase):
    async def test_no_prior_entry_returns_zero(self):
        pan = make_pan()
        pan.client.db.execute.return_value.fetchone = AsyncMock(return_value=None)
        result = await pan.get_cooldown_seconds(111)
        self.assertEqual(result, 0)

    async def test_recent_entry_returns_positive_cooldown(self):
        pan = make_pan()
        now = datetime.datetime.now()
        pan.client.db.execute.return_value.fetchone = AsyncMock(return_value=(now,))
        result = await pan.get_cooldown_seconds(111)
        self.assertGreater(result, 0)
        self.assertLessEqual(result, pan.cooldown)

    async def test_old_entry_returns_zero(self):
        pan = make_pan()
        old_time = datetime.datetime.now() - datetime.timedelta(seconds=120)
        pan.client.db.execute.return_value.fetchone = AsyncMock(return_value=(old_time,))
        result = await pan.get_cooldown_seconds(111)
        self.assertEqual(result, 0)


class TestPickANumberNoDiscriminator(unittest.IsolatedAsyncioTestCase):
    """Verify discriminator was removed from CSV generation."""

    async def test_gennumcsv_uses_name_without_discriminator(self):
        pan = make_pan()
        pan.client.db.execute.return_value.fetchall = AsyncMock(return_value=[(7, 111)])

        member = MagicMock()
        member.name = "TestUser"
        # discriminator should NOT be accessed — if it were, MagicMock would not raise
        # but we verify the name format doesn't include '#'
        message = MagicMock()
        message.channel.id = 100
        message.author.id = 999
        message.guild.get_member = MagicMock(return_value=member)
        message.channel.send = AsyncMock()

        await pan.cmd_gennumcsv(message)

        call_args = message.channel.send.call_args
        sent_file = call_args.kwargs.get("file") or call_args[1].get("file") or call_args[0][1]
        # discord.File wraps the underlying fp
        fp = sent_file.fp
        fp.seek(0)
        csv_content = fp.read()
        self.assertNotIn("#", csv_content)


if __name__ == "__main__":
    unittest.main()
