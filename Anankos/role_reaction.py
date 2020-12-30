class RoleReaction:
    def __init__(self, client, role_reaction, permanent_roles):
        self.client = client
        self.role_reaction = role_reaction
        self.permanent_roles = permanent_roles

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
        if message_id not in self.role_reaction:
            return (None, None)
        user_id = payload.user_id
        channel_id = payload.channel_id
        channel = self.client.get_channel(channel_id)
        emoji_roles = self.role_reaction[message_id]
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
        if lookup_str not in emoji_roles:
            return (None, None)
        role_id = emoji_roles[lookup_str]
        role = guild.get_role(role_id)
        if not role:
            return (None, None)
        if member.id in self.permanent_roles.keys() and role.id in self.permanent_roles.get(member.id, []):
            return (None, None)
        return (member, role)
