import discord
import re
from urlextract import URLExtract
from collections import deque
import asyncio
import aiohttp
import twitter
import datetime
import io
import os
from markdownify import markdownify
from bs4 import BeautifulSoup
import mimetypes
from urllib.parse import urljoin, urlparse
import ffmpeg
import tempfile

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
        self.bsky_pattern = re.compile("bsky.app\/profile\/(.+)\/post\/(\w+)")

        self.deviantart_url = "https://backend.deviantart.com/oembed?url={}"
        
        self.twitter_url = "https://cdn.syndication.twimg.com/tweet-result?features=tfw_timeline_list%3A%3Btfw_follower_count_sunset%3Atrue%3Btfw_tweet_edit_backend%3Aon%3Btfw_refsrc_session%3Aon%3Btfw_fosnr_soft_interventions_enabled%3Aon%3Btfw_mixed_media_15897%3Atreatment%3Btfw_experiments_cookie_expiration%3A1209600%3Btfw_show_birdwatch_pivots_enabled%3Aon%3Btfw_duplicate_scribes_to_settings%3Aon%3Btfw_use_profile_image_shape_enabled%3Aon%3Btfw_video_hls_dynamic_manifests_15082%3Atrue_bitrate%3Btfw_legacy_timeline_sunset%3Atrue%3Btfw_tweet_edit_frontend%3Aon&id={}&lang=en&token={}"
        self.fxtwitter_url = "https://api.fxtwitter.com/user/status/{}"
        self.vxtwitter_url = "https://api.vxtwitter.com/user/status/{}"

        self.pixiv_url = "https://www.pixiv.net/ajax/illust/{}?lang=en"
        self.pixiv_oembed_fallback_url = "https://embed.pixiv.net/decorate.php?illust_id={}"
        self.phixiv_url = "https://www.phixiv.net/api/info?id={}&language=en"

        self.bsky_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at%3A%2F%2F{}%2Fapp.bsky.feed.post%2F{}"

    def should_spoiler(self, url, content):
        if url.endswith("||"):
            return True
        url = re.escape(url)
        match = re.search("\|\|\s*{}\s+\|\|".format(url), content)
        if match:
            return True
        return False

    async def get_rich_embed(self, url, message, force_ignore_embeds):
        return await self.get_twitter_embed(url, message, force_ignore_embeds) or \
            await self.get_deviantart_embed(url, message, force_ignore_embeds) or \
            await self.get_pixiv_embed(url, message, force_ignore_embeds) or \
            await self.get_bsky_embed(url, message, force_ignore_embeds)

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
        if all(("twitter" in line or "pixiv" in line or "/x.com" in line or "bsky.app" in line) for line in urls) and not force_ignore_embeds:
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
                if attachment is not None:
                    attachment.spoiler = True
                em_msg = await channel.send("||https://corr.in/s ||", embed=embed, file=attachment)
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
        url = url.replace("mobile.twitter.com", "twitter.com").replace("fxtwitter.com", "twitter.com").replace("vxtwitter.com", "twitter.com").replace("/x.com", "/twitter.com")
        twitter_id = self.twitter_pattern.search(url)
        if not twitter_id:
            return None
        twitter_id = int(twitter_id.group(1))
        tweet_status = await self.fetch_fxtwitter(twitter_id)
        if not tweet_status or not tweet_status.get("mediaDetails", None) or len(tweet_status["mediaDetails"]) == 0:
            tweet_status = await self.fetch_vxtwitter(twitter_id)
            if not tweet_status or not tweet_status.get("mediaDetails", None) or len(tweet_status["mediaDetails"]) == 0:
                tweet_status = await self.fetch_twitter(twitter_id)
                if not tweet_status or not tweet_status.get("mediaDetails", None) or len(tweet_status["mediaDetails"]) == 0:
                    return None
        if message not in self.forced_embeds and not force_ignore_embeds:
            for embed in message.embeds:
                if embed.footer and embed.footer.text == "Twitter":
                    if url == embed.url:
                        return None
        imageobj = await self.fetch_image_fileobject(tweet_status["mediaDetails"][0]["media_url_https"] + "?name=large", "https://twitter.com/")
        embed = discord.Embed(
            description = tweet_status["text"],
            color = 1942002,
            url = url
        )
        embed.set_footer(text="Twitter", icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png")
        if "mp4" not in imageobj.filename:
            embed.set_image(url="attachment://{}".format(imageobj.filename))
        embed.set_author(
            name="{} ({})".format(tweet_status["user"]["name"], tweet_status["user"]["screen_name"]),
            url="https://twitter.com/{}".format(tweet_status["user"]["screen_name"]),
            icon_url=tweet_status["user"]["profile_image_url_https"]
        )
        #embed.add_field(name="Retweets", value=tweet_status.retweet_count, inline=True)
        embed.add_field(name="Likes", value=tweet_status["favorite_count"], inline=True)
        return embed, imageobj
    
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

    async def get_bsky_embed(self, url, message, force_ignore_embeds):
        bsky_link = self.bsky_pattern.search(url)
        if not bsky_link:
            return None
        username = bsky_link.group(1)
        postid = bsky_link.group(2)
        bsky = await self.fetch_bsky(username, postid)
        if not bsky:
            return None
        bsky = bsky["thread"]["post"]
        description = bsky["record"].get("text", None)
        image = None
        title = "{} (@{})".format(bsky["author"]["displayName"], bsky["author"]["handle"])
        if bsky.get("embed", None) and bsky["embed"]["$type"] == "app.bsky.embed.images#view":
            image = bsky["embed"]["images"][0]["fullsize"]
        if bsky.get("embed", None) and bsky["embed"]["$type"] == "app.bsky.embed.video#view":
            tmp_name = None
            with tempfile.NamedTemporaryFile(prefix="ana_bsky_", suffix=".mp4") as tmp:
                tmp_name = tmp.name
            (
                ffmpeg
                .input(bsky["embed"]["playlist"])
                .output(tmp_name, vcodec="copy")
                .run()
            )
            with open(tmp_name, "rb") as file:
                file_object = io.BytesIO(file.read())
                file_object.seek(0)
                image = discord.File(file_object, "image.mp4")
            os.remove(tmp_name)
        if image is None:
            return None
        if type(image) == str:
            imageobj = await self.fetch_image_fileobject(image, "https://bsky.social/")
        else:
            imageobj = image
        embed = discord.Embed(
            description = description,
            color = 686847,
            url = url,
            title = title
        )
        embed.set_footer(text="Bluesky", icon_url="https://bsky.social/about/images/favicon-32x32.png")
        if "mp4" not in imageobj.filename:
            embed.set_image(url="attachment://{}".format(imageobj.filename))
        return embed, imageobj

    async def fetch_bsky(self, username, postid):
        headers = {
            "user-agent": "Discordbot",
            "accept-language": "en-US,en;q=0.9",
            "referer": self.bsky_url.format(username, postid)
        }
        async with self.httpsession.get(self.bsky_url.format(username, postid), headers=headers) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            return result
        return None

    async def get_pixiv_embed(self, url, message, force_ignore_embeds):
        pixiv_link = self.pixiv_pattern.search(url)
        if not pixiv_link:
            return None
        pixiv_id = int(pixiv_link.group(1))
        pixiv = await self.fetch_pixiv(pixiv_id)
        if not pixiv:
            return None
        description = pixiv.get("description", None)
        if description:
            description = markdownify(description, strip=["a"])[:4000]
        embed = discord.Embed(
            description = description,
            color = 12123135,
            url = url,
            title = pixiv.get("title", None)
        )
        embed.set_footer(text="Pixiv", icon_url="https://s.pximg.net/common/images/apple-touch-icon.png")
        image = pixiv["urls"]["regular"]
        file_object = None
        file_extension = None
        if image is None:
            headers = {
                "user-agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
            }
            async with self.httpsession.get(self.phixiv_url.format(pixiv_id), headers=headers) as resp:
                if resp.status < 200 or resp.status >= 300:
                    image = None
                else:
                    response = await resp.json()
                    if len(response.get("image_proxy_urls", [])):
                        image = response["image_proxy_urls"][0]
        if image is not None:
            file_object = await self.fetch_image_fileobject(image, "https://www.pixiv.net/")
        else:
            image = self.pixiv_oembed_fallback_url.format(pixiv_id)
            file_object = await self.fetch_image_fileobject(image, "https://www.pixiv.net/")
        embed.set_image(url="attachment://{}".format(file_object.filename))
        embed.set_author(
            name="{}".format(pixiv["userName"]),
            url="https://www.pixiv.net/en/users/{}".format(pixiv["userId"])
        )
        return embed, file_object

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

    async def fetch_fxtwitter(self, tweet_id):
        headers = {
            "user-agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
        }
        async with self.httpsession.get(self.fxtwitter_url.format(tweet_id), headers=headers) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            media_details = [] if not result["tweet"].get("media", None) or not len(result["tweet"]["media"]["all"]) or result["tweet"]["media"]["all"][0].get("type", None) != "photo" else [{"media_url_https": result["tweet"]["media"]["all"][0]["url"]}]
            if media_details and result["tweet"]["media"].get("mosaic", None) and result["tweet"]["media"]["mosaic"].get("formats", None) and result["tweet"]["media"]["mosaic"]["formats"].get("jpeg", None):
                media_details = [{"media_url_https": result["tweet"]["media"]["mosaic"]["formats"]["jpeg"]}]
            if len(media_details) == 0 and result["tweet"].get("media", None) and result["tweet"]["media"].get("all", None) and len(result["tweet"]["media"]["all"]) and result["tweet"]["media"]["all"][0].get("url", None):
                media_details = [{"media_url_https": result["tweet"]["media"]["all"][0]["url"]}]
            elif len(media_details) == 0 and result["tweet"].get("media", None) and result["tweet"]["media"].get("all", None) and len(result["tweet"]["media"]["all"]) and result["tweet"]["media"]["all"][0].get("thumbnail_url", None):
                media_details = [{"media_url_https": result["tweet"]["media"]["all"][0]["thumbnail_url"]}]
            return {
                "user": {
                    "name": result["tweet"]["author"]["name"],
                    "screen_name": result["tweet"]["author"]["screen_name"],
                    "profile_image_url_https": result["tweet"]["author"]["avatar_url"],
                },
                "text": result["tweet"]["text"],
                "favorite_count": result["tweet"]["likes"],
                "mediaDetails": media_details
            }
        return None

    async def fetch_vxtwitter(self, tweet_id):
        headers = {
            "user-agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
        }
        async with self.httpsession.get(self.vxtwitter_url.format(tweet_id), headers=headers) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            media_details = [] if not result.get("media_extended", None) or not len(result["media_extended"]) or result["media_extended"][0].get("type", None) != "image" else [{"media_url_https": result["media_extended"][0]["url"]}]
            if media_details and result.get("combinedMediaUrl", None):
                media_details = [{"media_url_https": result["combinedMediaUrl"]}]
            if len(media_details) == 0 and result.get("media_extended", None) and len(result["media_extended"]) and result["media_extended"][0].get("url", None):
                media_details = [{"media_url_https": result["media_extended"][0]["url"]}]
            elif len(media_details) == 0 and result.get("media_extended", None) and len(result["media_extended"]) and result["media_extended"][0].get("thumbnail_url", None):
                media_details = [{"media_url_https": result["media_extended"][0]["thumbnail_url"]}]
            return {
                "user": {
                    "name": result["user_name"],
                    "screen_name": result["user_screen_name"],
                    "profile_image_url_https": result["user_profile_image_url"],
                },
                "text": result["text"],
                "favorite_count": result["likes"],
                "mediaDetails": media_details
            }
        return None

    async def fetch_image_fileobject(self, url, referer):
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.55 Safari/537.36",
            "accept-language": "en-US,en;q=0.9",
            "referer": referer
        }
        if "twimg" in url and "mp4" in url:
            url = urljoin(url, urlparse(url).path)
        async with self.httpsession.get(url, headers=headers) as resp:
            file_object = io.BytesIO(await resp.read())
            file_object.seek(0)
            content_type = resp.headers.get("content-type")
            if content_type == None:
                url = urljoin(url, urlparse(url).path)
                extension = "." + url.split(".")[-1]
                if len(extension) > 5:
                    extension = ".png"
            else:
                extension = mimetypes.guess_extension(content_type)
            if extension == ".jpe":
                extension = ".jpg"
            file_name = "image{}".format(extension)
            discord_file = discord.File(file_object, file_name)
            return discord_file

