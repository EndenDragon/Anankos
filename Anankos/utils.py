import discord

async def create_thread(message, name, auto_archive_duration=1440):
    channel = message.channel
    data = await message.guild._state.http.request(
        discord.http.Route(
            "POST", 
            "/channels/{channel_id}/messages/{message_id}/threads",
            channel_id=channel.id, 
            message_id=message.id
        ),
        json={"name": name, "auto_archive_duration": auto_archive_duration}
    )
    data["position"] = 100
    channel = discord.TextChannel(state=message.guild._state, guild=message.guild, data=data)
    return channel