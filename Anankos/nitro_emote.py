import re

class NitroEmote:
    def __init__(self, client):
        self.client = client
        self.regex = re.compile(":!([^\s^:]+):")

    async def on_message(self, message):
        if message.author.id == self.client.user.id or len(message.content) == 0:
            return
        emotes = set()
        for match in re.finditer(self.regex, message.content):
            match = match.group(1)
            if len(match) < 2:
                continue
            for emote in message.guild.emojis:
                if emote.animated and match.lower() in emote.name.lower():
                    emotes.add(emote)
                    break
        for emote in emotes:
            await message.add_reaction(emote)
