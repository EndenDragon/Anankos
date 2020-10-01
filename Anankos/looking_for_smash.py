import datetime

class LookingForSmash:
    def __init__(self, client, channel_id, role_id):
        self.client = client
        self.channel_id = channel_id
        self.role_id = role_id
        self.mention_last = None
        self.cooldown = 3600

    async def on_message(self, message):
        if message.channel.id != self.channel_id or message.author == self.client.user:
            return
        if not message.content.lower() == "!lfs":
            return
        cooldown = self.get_cooldown_seconds()
        if cooldown > 0:
            cool_str = self.format_cooldown(cooldown)
            await message.channel.send("{} Command is on cooldown: You must wait **{}** before you can send an another looking for smash mention!".format(message.author.mention, cool_str))
            return
        role = message.guild.get_role(self.role_id)
        await message.channel.send("{}\n__**{} would like to settle it in smash!**__".format(role.mention, message.author.mention))
        self.mention_last = datetime.datetime.now()

    def get_cooldown_seconds(self):
        if not self.mention_last:
            return 0
        elapsed_last = (datetime.datetime.now() - self.mention_last).total_seconds()
        time_left = max(self.cooldown - elapsed_last, 0)
        return round(time_left)

    def format_cooldown(self, cooldown):
        if cooldown <= 0:
            return "0s"
        cooldown_tmp = cooldown
        cool_hrs = 0
        cool_mins = 0
        cool_secs = 0
        while cooldown_tmp >= 3600:
            cool_hrs = cool_hrs + 1
            cooldown_tmp = cooldown_tmp - 3600
        while cooldown_tmp >= 60:
            cool_mins = cool_mins + 1
            cooldown_tmp = cooldown_tmp - 60
        cool_secs = cooldown_tmp
        cool_str = ""
        if cool_hrs:
            cool_str = cool_str + " {}h".format(cool_hrs)
        if cool_mins:
            cool_str = cool_str + " {}m".format(cool_mins)
        if cool_secs:
            cool_str = cool_str + " {}s".format(cool_secs)
        cool_str = cool_str.strip()
        return cool_str