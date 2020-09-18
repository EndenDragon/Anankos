class MassCorrinPing:
    def __init__(self, client):
        self.client = client
        self.past_offenders = []

    async def on_message(self, message):
        if not message.guild or message.author == self.client.user:
            return
        mentions = []
        for mention in message.mentions:
            if "corrin" in mention.name.lower() or (mention.nick and "corrin" in mention.nick.lower()):
                mentions.append(mention)
        if len(mentions) >= 3:
            await message.channel.send("{} has been too enthusiastic with their Corrin harem. The Corrin Conclave server members disgrunted with jealousy as they cast {} away. <:CorrinPing:630493356446973952>".format(message.author.mention, message.author.mention))
            note = "Spam is not tolerated at the Corrin Conclave. Please do not mass ping. "
            if message.author in self.past_offenders:
                note = note + "You have been banned."
            else:
                note = note + "**Last warning.**\nYou may reparticipate in the server with the following invite: https://Corr.in/"
            try:
                await message.author.send(note)
            except:
                pass
            if message.author in self.past_offenders:
                pass
                await message.author.ban(reason="Mass Corrin Ping", delete_message_days=0)
            else:
                self.past_offenders.append(message.author)
                await message.author.kick(reason="Mass Corrin Ping")
