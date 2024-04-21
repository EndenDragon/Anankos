from Anankos.utils import create_thread

class PollManager:
    def __init__(self, client, channel_id):
        self.client = client
        self.channel_id = channel_id

    async def on_message(self, message):
        if message.channel.id != self.channel_id and message.poll is not None and not message.author.permissions_in(message.channel).manage_messages:
            await message.delete()
            return

        if message.channel.id != self.channel_id:
            return

        if message.poll is None:
            await message.delete()
            return
        
        await create_thread(message, "Poll: " + message.poll["question"]["text"][:90], 4320)
