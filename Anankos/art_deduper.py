from collections import deque 
from urlextract import URLExtract
import asyncio
import re

class Image:
    def __init__(self, service, unique_id, message_obj):
        self.service = service
        self.unique_id = unique_id
        self.message_obj = message_obj

    def is_dupe(self, other):
        return self.service == other.service \
            and self.unique_id == other.unique_id \
            and (self.message_obj.created_at - other.message_obj.created_at).total_seconds() < 172800 # 2 days

class ArtDeduper:
    def __init__(self, client, image_channelids):
        self.client = client
        self.image_channelids = image_channelids
        self.cache = deque(maxlen=35)

        self.extractor = URLExtract()

        self.twitter_pattern = re.compile("twitter.com/\w+/status/(\d+)")
        self.pixiv_pattern = re.compile("www\.pixiv\.net\/en\/artworks\/(\d+)")

    def cache_message(self, message):
        urls = self.extractor.find_urls(message.content, True)
        for url in urls:
            image = self.get_image_obj(url, message)
            if image:
                self.cache.append(image)

    def get_duped_links(self, message):
        dupes = []
        urls = self.extractor.find_urls(message.content, True)
        for url in urls:
            image_needle = self.get_image_obj(url, message)
            if image_needle:
                for image_hay in self.cache:
                    if image_hay.is_dupe(image_needle):
                        dupes.append(url)
                        break
        return dupes

    def get_image_obj(self, url, message):
        # Twitter
        url = url.replace("mobile.twitter.com", "twitter.com")
        twitter_id = self.twitter_pattern.search(url)
        if twitter_id:
            twitter_id = int(twitter_id.group(1))
            return Image("Twitter", twitter_id, message)
        
        # Pixiv
        pixiv_link = self.pixiv_pattern.search(url)
        if pixiv_link:
            pixiv_id = int(pixiv_link.group(1))
            return Image("Pixiv", pixiv_id, message)

        return None

    async def on_message(self, message):
        if message.author.id == self.client.user.id or len(message.content) == 0:
            return
        if message.channel.id not in self.image_channelids:
            return
        dupes = self.get_duped_links(message)
        if len(dupes):
            try:
                await message.author.send("Sorry, the following images has already been posted in The Corrin Conclave, so your art submission was removed.\n{}".format("\n".join(dupes)))
                await message.delete()
            except:
                reply = await message.reply("Sorry {}, your submission was removed because there are images that has already been posted here.".format(message.author.mention))
                await message.delete()
                await asyncio.sleep(30)
                await reply.delete()
        else:
            self.cache_message(message)

    async def on_message_delete(self, message):
        if message.channel.id not in self.image_channelids or message.author == self.client.user:
            return
        for image in list(self.cache):
            if image.message_obj == message:
                self.cache.remove(image)

    