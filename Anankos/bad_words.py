import discord
import re
from unidecode import unidecode

class BadWords:
    def __init__(self, client, bad_words):
        self.client = client
        self.bad_words = bad_words
        self.re_bad_words = []
        for bad in self.bad_words:
            self.re_bad_words.append(
                re.compile(bad, re.IGNORECASE + re.MULTILINE + re.DOTALL)
            )

    async def on_message(self, message):
        await self.handle_bad_words(message)

    async def on_message_edit(self, before, after):
        await self.handle_bad_words(after)

    async def handle_bad_words(self, message):
        if message.author.id == self.client.user.id or not isinstance(message.author, discord.Member):
            return
        if message.author.permissions_in(message.channel).manage_messages or not message.guild.me.permissions_in(message.channel).manage_messages:
            return
        unidecoded = unidecode(message.content)
        regional_indi_normalized = self.convert_regional_indicators(message.content)
        delete = False
        for bad in self.re_bad_words:
            if bad.search(message.content) or bad.search(unidecoded) or bad.search(regional_indi_normalized):
                delete = True
                break
        if delete:
            try:
                await message.author.send("Hey {}! Thou shalt not speak the *forbidden word*!\nYou said: {}".format(message.author.mention, message.content))
            except:
                pass
            await message.delete()

    def convert_regional_indicators(self, message):
        start_ri = 127462
        start_latin = 65
        for i in range(27):
            ri = chr(start_ri + i)
            latin = chr(start_latin + i)
            message = message.replace(ri, latin)
        return message
