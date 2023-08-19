import discord
import re
from urlextract import URLExtract
from collections import deque
import asyncio
import aiohttp
import twitter
import datetime
import io

class ImageEmbed:
    def __init__(self, client, channel_ids, twitter_consumer_key, twitter_consumer_secret, twitter_access_token_key, twitter_access_token_secret):
        self.client = client
        self.channel_ids = channel_ids
        self.extractor = URLExtract()
        self.httpsession = aiohttp.ClientSession()
        self.message_cache = deque(maxlen=100)
        self.forced_embeds = deque(maxlen=100)
        self.ready = asyncio.Event()

        self.ready.set()

        self.twitter_pattern = re.compile("twitter.com/\w+/status/(\d+)")
        self.deviantart_pattern = re.compile("deviantart\.com.*.\d")
        self.pixiv_pattern = re.compile("www\.pixiv\.net\/en\/artworks\/(\d+)")

        self.deviantart_url = "https://backend.deviantart.com/oembed?url={}"
        
        self.twitter_url = "https://cdn.syndication.twimg.com/tweet-result?features=tfw_timeline_list%3A%3Btfw_follower_count_sunset%3Atrue%3Btfw_tweet_edit_backend%3Aon%3Btfw_refsrc_session%3Aon%3Btfw_fosnr_soft_interventions_enabled%3Aon%3Btfw_mixed_media_15897%3Atreatment%3Btfw_experiments_cookie_expiration%3A1209600%3Btfw_show_birdwatch_pivots_enabled%3Aon%3Btfw_duplicate_scribes_to_settings%3Aon%3Btfw_use_profile_image_shape_enabled%3Aon%3Btfw_video_hls_dynamic_manifests_15082%3Atrue_bitrate%3Btfw_legacy_timeline_sunset%3Atrue%3Btfw_tweet_edit_frontend%3Aon&id={}&lang=en&token={}"

        self.pixiv_session_url = "https://api.pixiv.moe/session"
        self.pixiv_url = "https://www.pixiv.net/ajax/illust/{}?lang=en"
        self.pixiv_oembed_fallback_url = "https://embed.pixiv.net/decorate.php?illust_id={}"

    def should_spoiler(self, url, content):
        url = re.escape(url)
        match = re.search("\|\|\s*{}\s+\|\|".format(url), content)
        if match:
            return True
        return False

    async def get_rich_embed(self, url, message, force_ignore_embeds):
        return await self.get_twitter_embed(url, message, force_ignore_embeds) or \
            await self.get_deviantart_embed(url, message, force_ignore_embeds) or \
            await self.get_pixiv_embed(url, message, force_ignore_embeds)

    async def on_message(self, message):
        await self.post_image_embeds(message)

    async def post_image_embeds(self, message, channel=None, force_ignore_embeds=False):
        if message.channel.id not in self.channel_ids or message.author == self.client.user:
            return
        if not channel:
            channel = message.channel
        self.ready.clear()
        urls = self.extractor.find_urls(message.content, True)
        urls = [url for url in urls if self.filter_link(url, message.content)]
        if all("fxtwitter" not in line and "vxtwitter" not in line and ("twitter" in line or "pixiv" in line) for line in urls) and not force_ignore_embeds:
            self.forced_embeds.append(message)
            if len(message.embeds):
                await message.edit(suppress=True)
        spoiler = []
        embeds = []
        for url in urls:
            rich_embed =  await self.get_rich_embed(url, message, force_ignore_embeds)
            if not rich_embed:
                continue
            embed, attachment = rich_embed
            if embed:
                embeds.append((embed, attachment))
                if self.should_spoiler(url, message.content):
                    spoiler.append(embed)
        to_cache = []
        for embed, attachment in embeds[:4]:
            if embed in spoiler:
                em_msg = await channel.send("||https://corr.in/s ||", embed=embed, files=attachment)
            else:
                em_msg = await channel.send(embed=embed, file=attachment)
            to_cache.append(em_msg)
        self.cache_message(message, to_cache)
        self.ready.set()

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
        await self.ready.wait()
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
        await self.ready.wait()
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

    async def get_twitter_embed(self, url, message, force_ignore_embeds):
        url = url.replace("mobile.twitter.com", "twitter.com")
        if "fxtwitter" in url.lower() or "vxtwitter" in url.lower():
            return None
        twitter_id = self.twitter_pattern.search(url)
        if not twitter_id:
            return None
        twitter_id = int(twitter_id.group(1))
        tweet_status = await self.fetch_twitter(twitter_id)
        if not tweet_status:
            return None
        if not tweet_status.get("mediaDetails", None) or len(tweet_status["mediaDetails"]) == 0:
            return None
        if message not in self.forced_embeds and not force_ignore_embeds:
            for embed in message.embeds:
                if embed.footer and embed.footer.text == "Twitter":
                    if url == embed.url:
                        return None
        embed = discord.Embed(
            description = tweet_status["text"],
            color = 1942002,
            url = url
        )
        embed.set_footer(text="Twitter", icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png")
        embed.set_image(url=tweet_status["mediaDetails"][0]["media_url_https"] + "?name=large")
        embed.set_author(
            name="{} ({})".format(tweet_status["user"]["name"], tweet_status["user"]["screen_name"]),
            url="https://twitter.com/{}".format(tweet_status["user"]["screen_name"]),
            icon_url=tweet_status["user"]["profile_image_url_https"]
        )
        #embed.add_field(name="Retweets", value=tweet_status.retweet_count, inline=True)
        embed.add_field(name="Likes", value=tweet_status["favorite_count"], inline=True)
        return embed, None
    
    async def get_deviantart_embed(self, url, message, force_ignore_embeds):
        da_link = self.deviantart_pattern.search(url)
        if not da_link:
            return None
        da_link = da_link[0]
        if message not in self.forced_embeds and not force_ignore_embeds:
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
            return embed, None

    async def get_pixiv_embed(self, url, message, force_ignore_embeds):
        pixiv_link = self.pixiv_pattern.search(url)
        if not pixiv_link:
            return None
        pixiv_id = int(pixiv_link.group(1))
        pixiv = await self.fetch_pixiv(pixiv_id)
        if not pixiv:
            return None
        embed = discord.Embed(
            description = pixiv.get("description", None),
            color = 12123135,
            url = url,
            title = pixiv.get("title", None)
        )
        embed.set_footer(text="Pixiv", icon_url="https://s.pximg.net/common/images/apple-touch-icon.png")
        image = pixiv["urls"]["regular"]
        file_object = None
        file_extension = None
        if image is not None:
            file_extension = image.split(".")[-1]
            headers = {
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.55 Safari/537.36",
                "accept-language": "en-US,en;q=0.9",
                "referer": "https://www.pixiv.net/"
            }
            async with self.httpsession.get(image, headers=headers) as resp:
                file_object = io.BytesIO(await resp.read())
                file_object.seek(0)
        else:
            image = self.pixiv_oembed_fallback_url.format(pixiv_id)
            async with self.httpsession.get(image) as resp:
                file_object = io.BytesIO(await resp.read())
                file_object.seek(0)
                content_type = resp.headers.get("content-type")
                if content_type == "image/png":
                    file_extension = "png"
                elif content_type == "image/jpg":
                    file_extension = "jpg"
                elif content_type == "image/jpeg":
                    file_extension = "jpeg"
                elif content_type == "image/gif":
                    file_extension = "gif"
                else:
                    print("Unknown content type {}".format(content_type))
        if file_extension is None:
            return None
        file_name = "image.{}".format(file_extension)
        discord_file = discord.File(file_object, file_name)
        embed.set_image(url="attachment://{}".format(file_name))
        embed.set_author(
            name="{}".format(pixiv["userName"]),
            url="https://www.pixiv.net/en/users/{}".format(pixiv["userId"])
        )
        return embed, discord_file

    async def fetch_pixiv(self, pixiv_id):
        now = datetime.datetime.now()
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.55 Safari/537.36",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://www.pixiv.net/en/artworks/{}".format(pixiv_id)
        }
        async with self.httpsession.get(self.pixiv_url.format(pixiv_id), headers=headers) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            return result["body"]
        return None

    async def fetch_twitter(self, tweet_id):
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.55 Safari/537.36",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://twitter.com/"
        }
        token = tweet_id
        async with self.httpsession.get(self.twitter_url.format(tweet_id, token), headers=headers) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            return result
        return None

