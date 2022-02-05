class AutoMod:
    def __init__(self, client):
        self.client = client

    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        reason = None
        if ".gift" in message.content:
            reason = "Sent a gift link (probably a Nitro scam from a compromised account)"
        elif len(message.mentions) >= 7:
            reason = "Pinged too many people ({} is way too many)".format(len(message.mentions))
        if reason:
            try:
                await message.author.send("**You have been banned from the Corrin Conclave Discord Server for the following reason, {}.**\nFor appeal, please contact EndenDragon#1337 on Discord or message u/EndenDragon on Reddit. Please present this message for context when appealing.".format(reason))
            except:
                pass
            try:
                await message.author.ban(reason=reason, delete_message_days=1)
            except:
                pass
            await message.channel.send("**{}#{} ({}) was banned automatically.**\n{}.".format(message.author.name, message.author.discriminator, message.author.mention, reason))
