import discord
import re
from urlextract import URLExtract
from collections import deque
import asyncio
import aiohttp
import twitter
import datetime

class ImageEmbed:
    def __init__(self, client, channel_ids, twitter_consumer_key, twitter_consumer_secret, twitter_access_token_key, twitter_access_token_secret):
        self.client = client
        self.channel_ids = channel_ids
        self.extractor = URLExtract()
        self.httpsession = aiohttp.ClientSession()
        self.message_cache = deque(maxlen=100)
        self.forced_embeds = deque(maxlen=100)

        self.twitter_pattern = re.compile("twitter.com/\w+/status/(\d+)")
        self.deviantart_pattern = re.compile("deviantart\.com.*.\d")
        self.pixiv_pattern = re.compile("www\.pixiv\.net\/en\/artworks\/(\d+)")

        self.deviantart_url = "https://backend.deviantart.com/oembed?url={}"

        self.twitterapi = twitter.Api(consumer_key=twitter_consumer_key,
                                        consumer_secret=twitter_consumer_secret,
                                        access_token_key=twitter_access_token_key,
                                        access_token_secret=twitter_access_token_secret,
                                        tweet_mode="extended")
        
        self.pixiv_session_url = "https://api.pixiv.moe/session"
        self.pixiv_url = "https://api.pixiv.moe/v2/illust/{}"
        self.pixiv_session = None
        self.pixiv_session_last_updated = None

    def should_spoiler(self, url, content):
        url = re.escape(url)
        match = re.search("\|\|\s*{}\s+\|\|".format(url), content)
        if match:
            return True
        return False

    async def get_rich_embed(self, url, message):
        return await self.get_twitter_embed(url, message) or \
            await self.get_deviantart_embed(url, message) or \
            await self.get_pixiv_embed(url, message)

    async def on_message(self, message):
        await self.post_image_embeds(message)

    async def post_image_embeds(self, message, channel=None):
        if message.channel.id not in self.channel_ids or message.author == self.client.user:
            return
        if not channel:
            channel = message.channel
        urls = self.extractor.find_urls(message.content, True)
        urls = [url for url in urls if self.filter_link(url, message.content)]
        if any(self.pixiv_pattern.search(line) for line in urls):
            self.forced_embeds.append(message)
            if len(message.embeds):
                await message.edit(suppress=True)
        spoiler = []
        embeds = []
        for url in urls:
            embed = await self.get_rich_embed(url, message)
            if embed:
                embeds.append(embed)
                if self.should_spoiler(url, message.content):
                    spoiler.append(embed)
        to_cache = []
        for embed in embeds[:4]:
            if embed in spoiler:
                em_msg = await channel.send("||https://corr.in/s ||", embed=embed)
            else:
                em_msg = await channel.send(embed=embed)
            to_cache.append(em_msg)
        self.cache_message(message, to_cache)

    def cache_message(self, message, embed_msgs):
        chosen = None
        for cache in self.message_cache:
            if message == cache["msg"]:
                chosen = cache
                break
        if not chosen:
            chosen = {"msg": message, "embed_msgs": []}
            self.message_cache.append(chosen)
        for em in embed_msgs:
            chosen["embed_msgs"].append(em)

    async def on_message_delete(self, message):
        if message.channel.id not in self.channel_ids or message.author == self.client.user:
            return
        chosen = None
        for cache in self.message_cache:
            if message == cache["msg"]:
                chosen = cache
                break
        if chosen:
            for to_delete in chosen["embed_msgs"]:
                try:
                    await to_delete.delete()
                except discord.errors.NotFound:
                    continue
            self.message_cache.remove(chosen)

    async def on_message_edit(self, before, after):
        urls = []
        if after in self.forced_embeds and len(after.embeds):
            await after.edit(suppress=True)
            return
        for embed in after.embeds:
            if embed.url:
                url = embed.url
                url = url.replace("mobile.twitter.com", "twitter.com")
                urls.append(url)
        await asyncio.sleep(0.5)
        chosen = None
        for cache in self.message_cache:
            if after == cache["msg"]:
                chosen = cache
                break
        if chosen:
            for potential in list(chosen["embed_msgs"]):
                if len(potential.embeds) and potential.embeds[0].url in urls:
                    try:
                        await potential.delete()
                    except discord.errors.NotFound:
                        continue
                    chosen["embed_msgs"].remove(potential)

    def filter_link(self, url, message_content):
        return message_content.count("<" + url + ">") < message_content.count(url)

    async def get_twitter_embed(self, url, message):
        url = url.replace("mobile.twitter.com", "twitter.com")
        twitter_id = self.twitter_pattern.search(url)
        if not twitter_id:
            return None
        twitter_id = int(twitter_id.group(1))
        tweet_status = self.twitterapi.GetStatus(twitter_id)
        if not tweet_status:
            return None
        if not hasattr(tweet_status, "media") or len(tweet_status.media) == 0:
            return None
        if message not in self.forced_embeds:
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
        if message not in self.forced_embeds:
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
            embed.set_author(name=result["author_name"], url=result["author_url"], icon_url="https://st.deviantart.net/eclipse/icons/android-192.png")
            return embed

    async def get_pixiv_embed(self, url, message):
        pixiv_link = self.pixiv_pattern.search(url)
        if not pixiv_link:
            return None
        pixiv_id = int(pixiv_link.group(1))
        pixiv = await self.fetch_pixiv(pixiv_id)
        if not pixiv:
            return None
        pixiv = pixiv["illust"]
        embed = discord.Embed(
            description = pixiv.get("caption", None),
            color = 12123135,
            url = url,
            title = pixiv.get("title", None)
        )
        embed.set_footer(text="Pixiv", icon_url="https://s.pximg.net/common/images/apple-touch-icon.png")
        embed.set_image(url="https://api.pixiv.moe/image/{}".format(pixiv["image_urls"]["original"][8:]))
        embed.set_author(
            name="{}".format(pixiv["user"]["name"]),
            url="https://www.pixiv.net/en/users/{}".format(pixiv["user"]["id"])
        )
        return embed

    async def fetch_pixiv(self, pixiv_id):
        now = datetime.datetime.now()
        if not self.pixiv_session or self.pixiv_session_last_updated + datetime.timedelta(days=1) < now:
            async with self.httpsession.get(self.pixiv_session_url) as resp:
                if resp.status < 200 or resp.status >= 300:
                    return None
                result = await resp.json()
                self.pixiv_session = result["response"]["access_token"]
                self.pixiv_session_last_updated = now
        async with self.httpsession.get(self.pixiv_url.format(pixiv_id), headers={"x-kotori-token": self.pixiv_session}) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            return result["response"]
        return None
