import discord
import re

class BadWords:
    def __init__(self, client, bad_words):
        self.client = client
        self.bad_words = bad_words
        self.pattern = re.compile('[\W_]+')

    async def on_message(self, message):
        await self.handle_bad_words(message)

    async def on_message_edit(self, before, after):
        await self.handle_bad_words(after)

    async def handle_bad_words(self, message):
        if message.author.id == self.client.user.id or not isinstance(message.author, discord.Member):
            return
        if message.author.permissions_in(message.channel).manage_messages or not message.guild.me.permissions_in(message.channel).manage_messages:
            return
        delete = False
        content = self.pattern.sub('', message.content.lower())
        for bad in self.bad_words:
            if bad.lower() in content:
                delete = True
                break
        if delete:
            await message.channel.send("Hey {}! Thou shalt not speak the *forbidden word*!".format(message.author.mention))
            await message.delete()
