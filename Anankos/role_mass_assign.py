import asyncio

class RoleMassAssign:
    def __init__(self, client):
        self.client = client
        self.target_role_id = 1478332387250405546  # Alluring Darkness
        self.excluded_role_id = 635378577831100466  # Lady of the Lake

    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.content.startswith("!role"):
            return

        guild = message.guild
        if not guild:
            return

        target_role = guild.get_role(self.target_role_id)
        excluded_role = guild.get_role(self.excluded_role_id)

        if not target_role or not excluded_role:
            await message.channel.send("Role not found.")
            return

        await message.channel.send(
            f"Starting role assignment for {len(guild.members)} members..."
        )

        added_count = 0
        checked_count = 0

        for member in guild.members:
            checked_count += 1

            if member.bot:
                continue

            if excluded_role in member.roles:
                continue

            if target_role in member.roles:
                continue

            try:
                await member.add_roles(target_role)
                added_count += 1

                # Small delay to prevent aggressive rate limiting
                await asyncio.sleep(0.25)

            except Exception as e:
                print(f"Failed for {member.id}: {e}")

            # Progress update every 50 members
            if checked_count % 50 == 0:
                await message.channel.send(
                    f"Progress: {checked_count}/{len(guild.members)} checked | {added_count} roles added"
                )

        await message.channel.send(
            f"✅ Complete.\nChecked: {checked_count}\nRoles Added: {added_count}"
        )