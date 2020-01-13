class RoleReaction:
    def __init__(self, client, message_id, emoji_roles):
        self.client = client
        self.message_id = message_id
        self.emoji_roles = emoji_roles

    async def on_raw_reaction_add(self, payload):
        member, role = await self.get_member_and_role(payload)
        if not member or not role:
            return
        await member.add_roles(role)

    async def on_raw_reaction_remove(self, payload):
        member, role = await self.get_member_and_role(payload)
        if not member or not role:
            return
        await member.remove_roles(role)

    async def get_member_and_role(self, payload):
        message_id = payload.message_id
        if message_id != self.message_id:
            return (None, None)
        user_id = payload.user_id
        channel_id = payload.channel_id
        channel = self.client.get_channel(channel_id)
        if not channel:
            return (None, None)
        guild = channel.guild
        member = guild.get_member(user_id)
        if not member:
            return (None, None)
        emoji = payload.emoji
        lookup_str = None
        if emoji.is_custom_emoji():
            lookup_str = emoji.id
        if emoji.is_unicode_emoji():
            lookup_str = emoji.name
        if lookup_str not in self.emoji_roles:
            return (None, None)
        role_id = self.emoji_roles[lookup_str]
        role = guild.get_role(role_id)
        if not role:
            return (None, None)
        return (member, role)
