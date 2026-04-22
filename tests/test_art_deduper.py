import unittest
import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from collections import deque

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.art_deduper import ArtDeduper, Image


def make_message(content, channel_id=100, author_id=200, created_at=None):
    msg = MagicMock()
    msg.content = content
    msg.channel.id = channel_id
    msg.author.id = author_id
    msg.author.bot = False
    msg.created_at = created_at or datetime.datetime(2024, 1, 1)
    return msg


class TestImage(unittest.TestCase):
    def _make_msg(self, ts):
        m = MagicMock()
        m.created_at = ts
        return m

    def test_is_dupe_same_service_and_id_within_2_days(self):
        ts = datetime.datetime(2024, 1, 1)
        a = Image("Twitter", 123, self._make_msg(ts))
        b = Image("Twitter", 123, self._make_msg(ts))
        self.assertTrue(a.is_dupe(b))

    def test_is_not_dupe_different_id(self):
        ts = datetime.datetime(2024, 1, 1)
        a = Image("Twitter", 123, self._make_msg(ts))
        b = Image("Twitter", 456, self._make_msg(ts))
        self.assertFalse(a.is_dupe(b))

    def test_is_not_dupe_different_service(self):
        ts = datetime.datetime(2024, 1, 1)
        a = Image("Twitter", 123, self._make_msg(ts))
        b = Image("Pixiv", 123, self._make_msg(ts))
        self.assertFalse(a.is_dupe(b))

    def test_is_not_dupe_older_than_2_days(self):
        ts_old = datetime.datetime(2024, 1, 1)
        ts_new = datetime.datetime(2024, 1, 4)  # 3 days later
        a = Image("Twitter", 123, self._make_msg(ts_old))
        b = Image("Twitter", 123, self._make_msg(ts_new))
        self.assertFalse(a.is_dupe(b))


class TestArtDeduper(unittest.TestCase):
    def setUp(self):
        client = MagicMock()
        client.user.id = 999
        self.deduper = ArtDeduper(client, image_channelids=[100])

    def test_get_image_obj_twitter(self):
        img = self.deduper.get_image_obj("https://twitter.com/user/status/123456789", MagicMock())
        self.assertIsNotNone(img)
        self.assertEqual(img.service, "Twitter")
        self.assertEqual(img.unique_id, 123456789)

    def test_get_image_obj_x_com(self):
        url = "https://twitter.com/user/status/999"
        img = self.deduper.get_image_obj(url, MagicMock())
        self.assertIsNotNone(img)
        self.assertEqual(img.service, "Twitter")

    def test_get_image_obj_pixiv(self):
        img = self.deduper.get_image_obj("https://www.pixiv.net/en/artworks/987654", MagicMock())
        self.assertIsNotNone(img)
        self.assertEqual(img.service, "Pixiv")
        self.assertEqual(img.unique_id, 987654)

    def test_get_image_obj_bluesky(self):
        img = self.deduper.get_image_obj("https://bsky.app/profile/user.bsky.social/post/abc123", MagicMock())
        self.assertIsNotNone(img)
        self.assertEqual(img.service, "Bluesky")
        self.assertEqual(img.unique_id, "abc123")

    def test_get_image_obj_unknown_url(self):
        img = self.deduper.get_image_obj("https://example.com/image.png", MagicMock())
        self.assertIsNone(img)

    def test_get_duped_links_empty_cache(self):
        msg = make_message("https://twitter.com/user/status/111")
        dupes = self.deduper.get_duped_links(msg)
        self.assertEqual(dupes, [])

    def test_get_duped_links_detects_duplicate(self):
        ts = datetime.datetime(2024, 1, 1)
        old_msg = make_message("https://twitter.com/user/status/111", created_at=ts)
        self.deduper.cache_message(old_msg)

        new_msg = make_message("https://twitter.com/user/status/111", created_at=ts)
        dupes = self.deduper.get_duped_links(new_msg)
        self.assertEqual(len(dupes), 1)
        self.assertIn("twitter.com/user/status/111", dupes[0])

    def test_cache_message_adds_to_cache(self):
        msg = make_message("https://www.pixiv.net/en/artworks/12345")
        self.deduper.cache_message(msg)
        self.assertEqual(len(self.deduper.cache), 1)
        self.assertEqual(self.deduper.cache[0].service, "Pixiv")

    def test_cache_message_ignores_unknown_urls(self):
        msg = make_message("hello world no urls here")
        self.deduper.cache_message(msg)
        self.assertEqual(len(self.deduper.cache), 0)

    def test_no_dupe_for_different_twitter_id(self):
        ts = datetime.datetime(2024, 1, 1)
        self.deduper.cache_message(make_message("https://twitter.com/user/status/111", created_at=ts))
        new_msg = make_message("https://twitter.com/user/status/222", created_at=ts)
        dupes = self.deduper.get_duped_links(new_msg)
        self.assertEqual(dupes, [])

    def test_url_normalization_x_com(self):
        ts = datetime.datetime(2024, 1, 1)
        # cache via twitter.com URL
        self.deduper.cache_message(make_message("https://twitter.com/user/status/555", created_at=ts))
        # detect via x.com URL (normalized to twitter.com internally)
        new_msg = make_message("https://twitter.com/user/status/555", created_at=ts)
        dupes = self.deduper.get_duped_links(new_msg)
        self.assertEqual(len(dupes), 1)


class TestArtDeduperAsync(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        client = MagicMock()
        client.user.id = 999
        self.deduper = ArtDeduper(client, image_channelids=[100])

    async def test_on_message_wrong_channel_ignored(self):
        msg = make_message("https://twitter.com/user/status/123", channel_id=999)
        msg.author.id = 1
        await self.deduper.on_message(msg)
        self.assertEqual(len(self.deduper.cache), 0)

    async def test_on_message_caches_new_url(self):
        msg = make_message("https://twitter.com/user/status/123", channel_id=100)
        msg.author.id = 1
        await self.deduper.on_message(msg)
        self.assertEqual(len(self.deduper.cache), 1)

    async def test_on_message_delete_removes_from_cache(self):
        ts = datetime.datetime(2024, 1, 1)
        msg = make_message("https://www.pixiv.net/en/artworks/99999", channel_id=100, created_at=ts)
        # Use a plain object as author so == comparison uses identity (not MagicMock's truthy __eq__)
        msg.author = object()
        self.deduper.cache_message(msg)
        self.assertEqual(len(self.deduper.cache), 1)

        await self.deduper.on_message_delete(msg)
        self.assertEqual(len(self.deduper.cache), 0)


if __name__ == "__main__":
    unittest.main()
