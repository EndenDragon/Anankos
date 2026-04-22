import unittest
from unittest.mock import MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.image_embed import ImageEmbed


def make_image_embed():
    client = MagicMock()
    client.user.id = 999
    return ImageEmbed(client, channel_ids=[100])


class TestShouldSpoiler(unittest.TestCase):
    def setUp(self):
        self.ie = make_image_embed()

    def test_url_ends_with_pipe(self):
        self.assertTrue(self.ie.should_spoiler("https://twitter.com/x/status/1||", ""))

    def test_url_wrapped_in_spoiler_tags(self):
        url = "https://twitter.com/x/status/1"
        content = "|| https://twitter.com/x/status/1 ||"
        self.assertTrue(self.ie.should_spoiler(url, content))

    def test_url_not_in_spoiler(self):
        url = "https://twitter.com/x/status/1"
        content = "check this https://twitter.com/x/status/1"
        self.assertFalse(self.ie.should_spoiler(url, content))


class TestFilterLink(unittest.TestCase):
    def setUp(self):
        self.ie = make_image_embed()

    def test_unescaped_url_passes(self):
        url = "https://twitter.com/x/status/1"
        content = "look https://twitter.com/x/status/1"
        self.assertTrue(self.ie.filter_link(url, content))

    def test_escaped_url_filtered(self):
        url = "https://twitter.com/x/status/1"
        content = "<https://twitter.com/x/status/1>"
        self.assertFalse(self.ie.filter_link(url, content))

    def test_mixed_one_escaped_one_not(self):
        url = "https://twitter.com/x/status/1"
        content = "<https://twitter.com/x/status/1> https://twitter.com/x/status/1"
        self.assertTrue(self.ie.filter_link(url, content))


class TestSetQueryParam(unittest.TestCase):
    def setUp(self):
        self.ie = make_image_embed()

    def test_adds_new_param(self):
        url = "https://pbs.twimg.com/media/img.jpg"
        result = self.ie.set_query_param(url, "name", "large")
        self.assertIn("name=large", result)

    def test_replaces_existing_param(self):
        url = "https://pbs.twimg.com/media/img.jpg?name=small"
        result = self.ie.set_query_param(url, "name", "large")
        self.assertIn("name=large", result)
        self.assertNotIn("name=small", result)

    def test_keep_others_true(self):
        url = "https://pbs.twimg.com/media/img.jpg?format=jpg&name=small"
        result = self.ie.set_query_param(url, "name", "large", keep_others=True)
        self.assertIn("format=jpg", result)
        self.assertIn("name=large", result)

    def test_keep_others_false(self):
        url = "https://pbs.twimg.com/media/img.jpg?format=jpg&name=small"
        result = self.ie.set_query_param(url, "name", "large", keep_others=False)
        self.assertNotIn("format=jpg", result)
        self.assertIn("name=large", result)


class TestTwitterPattern(unittest.TestCase):
    def setUp(self):
        self.ie = make_image_embed()

    def test_matches_twitter_url(self):
        m = self.ie.twitter_pattern.search("https://twitter.com/user/status/123456789")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "123456789")

    def test_does_not_match_non_twitter(self):
        m = self.ie.twitter_pattern.search("https://example.com/page")
        self.assertIsNone(m)


class TestPixivPattern(unittest.TestCase):
    def setUp(self):
        self.ie = make_image_embed()

    def test_matches_pixiv_url(self):
        m = self.ie.pixiv_pattern.search("https://www.pixiv.net/en/artworks/987654321")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "987654321")

    def test_does_not_match_non_pixiv(self):
        m = self.ie.pixiv_pattern.search("https://example.com")
        self.assertIsNone(m)


class TestBskyPattern(unittest.TestCase):
    def setUp(self):
        self.ie = make_image_embed()

    def test_matches_bsky_url(self):
        m = self.ie.bsky_pattern.search("https://bsky.app/profile/user.bsky.social/post/abc123xyz")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "user.bsky.social")
        self.assertEqual(m.group(2), "abc123xyz")

    def test_does_not_match_non_bsky(self):
        m = self.ie.bsky_pattern.search("https://mastodon.social/@user")
        self.assertIsNone(m)


if __name__ == "__main__":
    unittest.main()
