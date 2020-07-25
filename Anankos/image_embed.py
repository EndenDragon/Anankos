import discord
import re
from urlextract import URLExtract
import asyncio
import aiohttp
import twitter

class ImageEmbed:
    def __init__(self, client, channel_ids, twitter_consumer_key, twitter_consumer_secret, twitter_access_token_key, twitter_access_token_secret):
        self.client = client
        self.channel_ids = channel_ids
        self.extractor = URLExtract()
        self.httpsession = aiohttp.ClientSession()

        self.twitter_pattern = re.compile("twitter.com/\w+/status/(\d+)")
        self.deviantart_pattern = re.compile("deviantart\.com.*.\d")

        self.deviantart_url = "https://backend.deviantart.com/oembed?url={}"

        self.twitterapi = twitter.Api(consumer_key=twitter_consumer_key,
                                        consumer_secret=twitter_consumer_secret,
                                        access_token_key=twitter_access_token_key,
                                        access_token_secret=twitter_access_token_secret,
                                        tweet_mode="extended")

    async def on_message(self, message):
        if message.channel.id not in self.channel_ids or message.author == self.client.user:
            return
        await asyncio.sleep(4)
        urls = self.extractor.find_urls(message.content, True)
        urls = [url for url in urls if self.filter_link(url, message.content)]
        embeds = []
        for url in urls:
            embeds.append(await self.get_twitter_embed(url, message))
            embeds.append(await self.get_deviantart_embed(url, message))
        embeds = [embed for embed in embeds if embed]
        for embed in embeds[:4]:
            await message.channel.send(embed=embed)

    def filter_link(self, url, message_content):
        return message_content.count("<" + url + ">") < message_content.count(url)

    async def get_twitter_embed(self, url, message):
        twitter_id = self.twitter_pattern.search(url)
        if not twitter_id:
            return None
        twitter_id = int(twitter_id.group(1))
        tweet_status = self.twitterapi.GetStatus(twitter_id)
        if not tweet_status:
            return None
        if not hasattr(tweet_status, "media") or len(tweet_status.media) == 0:
            return None
        for embed in message.embeds:
            if embed.footer and embed.footer.text == "Twitter":
                if url == embed.url:
                    return None
        embed = discord.Embed(
            description = tweet_status.full_text,
            color = 1942002,
            url = url
        )
        embed.set_footer(text="Twitter", icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png")
        embed.set_image(url=tweet_status.media[0].media_url_https)
        embed.set_author(
            name="{} ({})".format(tweet_status.user.name, tweet_status.user.screen_name),
            url="https://twitter.com/{}".format(tweet_status.user.screen_name),
            icon_url=tweet_status.user.profile_image_url_https
        )
        embed.add_field(name="Retweets", value=tweet_status.retweet_count, inline=True)
        embed.add_field(name="Likes", value=tweet_status.favorite_count, inline=True)
        return embed
    
    async def get_deviantart_embed(self, url, message):
        da_link = self.deviantart_pattern.search(url)
        if not da_link:
            return None
        da_link = da_link[0]
        for embed in message.embeds:
            if embed.provider and embed.provider.name == "DeviantArt":
                if da_link in embed.url:
                    return None
        async with self.httpsession.get(self.deviantart_url.format(da_link)) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            if result["type"] != "photo":
                return None
            embed = discord.Embed(
                title = "{} by {} on DeviantArt".format(result["title"], result["author_name"]),
                color = 395021,
                url = url
            )
            embed.set_image(url=result["url"])
            embed.set_author(name=result["author_name"], url=result["author_url"], icon_url="https://i.imgur.com/PS1B721.png?1")
            return embed
