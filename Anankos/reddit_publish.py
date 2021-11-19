from urlextract import URLExtract
import aiohttp
import html
import discord
import asyncpraw

class RedditPublish:
    def __init__(self, client, source_chan_id, dest_chan_id, client_id, client_secret):
        self.client = client
        self.source_chan_id = source_chan_id
        self.dest_chan_id = dest_chan_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.extractor = URLExtract()
        self.httpsession = aiohttp.ClientSession()
        self.reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="Anankos Discord Bot for Corrin Conclave Community https://github.com/EndenDragon/Anankos",
        )

        self.bg_task = self.client.loop.create_task(self.background_task())

    async def background_task(self):
        await self.client.wait_until_ready()
        subreddit = await self.reddit.subreddit("CorrinConclave")
        async for submission in subreddit.stream.submissions(skip_existing=True):
            try:
                permalink = "https://reddit.com" + submission.permalink
                embed = await self.get_rich_embed(permalink)
                if embed:
                    channel = self.client.get_channel(self.source_chan_id)
                    await channel.send(embed=embed)
            except Exception as e:
                print(e)

    async def on_message(self, message):
        if message.channel.id != self.source_chan_id:
            return
        if (message.author.name == "MEE6" or message.author == self.client.user) and message.author.bot and len(message.embeds):
            await message.add_reaction("📤")
        elif message.content.startswith("!publish "):
            urls = self.extractor.find_urls(message.content, True)
            if len(urls) == 0:
                return
            url = urls[0]
            await self.publish_reddit_link(url)

    async def on_raw_reaction_add(self, payload):
        if payload.channel_id != self.source_chan_id or not payload.member or payload.member == self.client.user or payload.member.bot:
            return
        channel = self.client.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if len(message.embeds) == 0:
            return
        for reaction in message.reactions:
            if reaction.me and str(reaction.emoji) == "✅":
                return
        if payload.emoji.is_unicode_emoji() and payload.emoji.name == "📤":
            url = message.embeds[0].author.url
            await self.publish_reddit_link(url)
            await message.add_reaction("✅")

    async def get_rich_embed(self, url):
        if "reddit.com" not in url:
            return None
        if url.endswith("/"):
            url = url[:-1]
        url = url + ".json"
        async with self.httpsession.get(url) as resp:
            if resp.status < 200 or resp.status >= 300:
                return None
            result = await resp.json()
            result = result[0]["data"]["children"][0]["data"]
            if result["over_18"]:
                return None
            post_title = result["title"]
            post_author = result["author"]
            post_url = "https://reddit.com" + result["permalink"]
            subreddit_name = result["subreddit"]
            image_url = None
            text = result.get("selftext", None)
            if result.get("preview", None) and result["preview"].get("images", []) and len(result["preview"]["images"]):
                image_url = result["preview"]["images"][0]["source"]["url"]
            elif result.get("media_metadata", None):
                key = list(result["media_metadata"].keys())[0]
                image_url = result["media_metadata"][key]["s"]["u"]
            if image_url:
                image_url = html.unescape(image_url)
            if text and len(text) > 230:
                text = text[:230].strip() + "..."
            embed = discord.Embed(
                title = post_title,
                color = 16721408,
                url = image_url if image_url else post_url,
                description = text
            )
            if image_url:
                embed.set_image(url=image_url)
            embed.set_author(
                name="New{} post on /r/{}".format(" image" if image_url else "", subreddit_name),
                url=post_url
            )
            embed.add_field(name="Post Author", value="/u/{}".format(post_author), inline=True)
            return embed
        return None

    async def publish_reddit_link(self, url):
        embed = await self.get_rich_embed(url)
        if embed:
            channel = self.client.get_channel(self.dest_chan_id)
            await channel.send(embed=embed)
