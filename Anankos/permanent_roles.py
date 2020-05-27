class PermanentRoles:
    def __init__(self, client, permanent_roles):
        self.client = client
        self.permanent_roles = permanent_roles

    async def on_member_join(self, member):
        role_ids = self.permanent_roles.get(member.id, [])
        if role_ids:
            roles = []
            for roleid in role_ids:
                role = member.guild.get_role(roleid)
                if role:
                    roles.append(role)
            if roles:
                await member.add_roles(*roles, reason="Automatically added role per bot config")
    