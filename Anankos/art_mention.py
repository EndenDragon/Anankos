import datetime

class ArtMention:
    def __init__(self, client, image_channelids, art_mention):
        self.client = client
        self.image_channelids = image_channelids
        self.art_mention = art_mention
        self.mention_last = {}
        self.cooldown = 30

    async def on_message(self, message):
        if message.channel.id not in self.image_channelids:
            return
        content_split = message.content.lower().split()
        roles_to_mention = set()
        for character, role_id in self.art_mention.items():
            character = character.lower()
            if "@@{}".format(character) not in content_split:
                continue
            if self.get_cooldown_seconds(character) > 0:
                continue
            self.mention_last[character] = datetime.datetime.now()
            role = message.channel.guild.get_role(role_id)
            if not role:
                continue
            roles_to_mention.add(role)
        if len(roles_to_mention):
            mentions = ""
            for role in roles_to_mention:
                mentions = mentions + role.mention + " "
            mention_msg = "{}: {}".format(message.author.mention, mentions)
            await message.channel.send(mention_msg)

    def get_cooldown_seconds(self, name):
        if name not in self.mention_last:
            return 0
        elapsed_last = (datetime.datetime.now() - self.mention_last[name]).total_seconds()
        time_left = max(self.cooldown - elapsed_last, 0)
        return round(time_left)