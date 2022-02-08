import discord

class Activities:
    def __init__(self, client, channel_id):
        self.client = client
        self.channel_id = channel_id

        self.activity_options = {
            "poker": 755827207812677713,
            "betrayal": 773336526917861400,
            "youtube": 880218394199220334,
            "fishington": 814288819477020702,
            "chess": 832012774040141894,
            "checkers": 832013003968348200,
            "letter": 879863686565621790,
            "word": 879863976006127627,
            "sketchheads": 902271654783242291,
            "spellcast": 852509694341283871,
            "sketchyartist": 879864070101172255,
            "awkword": 879863881349087252,
            "ocho": 832025144389533716,
        }

    async def create_embedded_invite(self, channel, target_application_id):
        data = await channel._state.http.request(
            discord.http.Route(
                "POST", 
                "/channels/{channel_id}/invites",
                channel_id=channel.id
            ),
            json={
                "max_age": 0,
                "target_type": 2,
                "target_application_id": target_application_id
            }
        )
        return discord.Invite.from_incomplete(data=data, state=channel._state)

    async def on_message(self, message):
        content = message.content.lower().split()
        if not content:
            return
        if content[0] != "!activity":
            return
        if len(content) < 2:
            await message.reply("Please include an activity: !activity [{}]".format(",".join(self.activity_options.keys())))
            return
        activity_type = content[1]
        if activity_type not in self.activity_options.keys():
            await message.reply("{} is not a valid option of: {}".format(activity_type, ",".join(self.activity_options.keys())))
            return
        channel = message.guild.get_channel(self.channel_id)
        if not channel:
            return
        invite = await self.create_embedded_invite(channel, self.activity_options[activity_type])
        await message.reply("Click this link to join **{}**! {}".format(activity_type, invite.url))
