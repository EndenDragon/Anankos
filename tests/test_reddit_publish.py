import unittest
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.reddit_publish import RedditPublish


def make_reddit_publish():
    client = MagicMock()
    client.user.id = 999
    rp = RedditPublish.__new__(RedditPublish)
    rp.client = client
    rp.source_chan_id = 100
    rp.dest_chan_id = 200
    from urlextract import URLExtract
    rp.extractor = URLExtract()
    rp.httpsession = None
    rp.reddit = MagicMock()
    return rp


class TestEmojiCheck(unittest.IsolatedAsyncioTestCase):
    """Verify the emoji check was updated from is_unicode_emoji() to emoji.id is None."""

    async def test_unicode_emoji_triggers_publish(self):
        rp = make_reddit_publish()

        # Unicode emoji has id=None
        emoji = MagicMock()
        emoji.id = None
        emoji.name = "📤"

        member = MagicMock()
        member.bot = False
        member.__eq__ = lambda s, o: False  # not the bot user

        payload = MagicMock()
        payload.channel_id = rp.source_chan_id
        payload.member = member
        payload.emoji = emoji

        reaction = MagicMock()
        reaction.me = False
        reaction.emoji = "✅"

        embed = MagicMock()
        embed.author.url = "https://reddit.com/r/test/comments/abc/title"

        message = MagicMock()
        message.embeds = [embed]
        message.reactions = [reaction]
        message.add_reaction = AsyncMock()

        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=message)
        rp.client.get_channel = MagicMock(return_value=channel)

        rp.publish_reddit_link = AsyncMock()
        rp.client.user.__eq__ = lambda s, o: False

        await rp.on_raw_reaction_add(payload)
        rp.publish_reddit_link.assert_called_once_with(embed.author.url)

    async def test_custom_emoji_does_not_trigger(self):
        rp = make_reddit_publish()

        # Custom emoji has non-None id
        emoji = MagicMock()
        emoji.id = 12345
        emoji.name = "custom_emoji"

        member = MagicMock()
        member.bot = False

        payload = MagicMock()
        payload.channel_id = rp.source_chan_id
        payload.member = member
        payload.emoji = emoji

        reaction = MagicMock()
        reaction.me = False

        message = MagicMock()
        message.embeds = [MagicMock()]
        message.reactions = [reaction]
        message.add_reaction = AsyncMock()

        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=message)
        rp.client.get_channel = MagicMock(return_value=channel)

        rp.publish_reddit_link = AsyncMock()
        rp.client.user.__eq__ = lambda s, o: False

        await rp.on_raw_reaction_add(payload)
        rp.publish_reddit_link.assert_not_called()

    async def test_wrong_channel_ignored(self):
        rp = make_reddit_publish()
        payload = MagicMock()
        payload.channel_id = 9999  # not source_chan_id
        payload.member = MagicMock()

        rp.publish_reddit_link = AsyncMock()
        rp.client.get_channel = MagicMock()

        await rp.on_raw_reaction_add(payload)
        rp.publish_reddit_link.assert_not_called()

    async def test_publish_message_calls_native_api(self):
        rp = make_reddit_publish()
        message = MagicMock()
        message.publish = AsyncMock()
        await rp.publish_message(message)
        message.publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
