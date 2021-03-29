import datetime
import discord
import asyncio

class ArtMention:
    def __init__(self, client, image_channelids, base_role_id):
        self.client = client
        self.image_channelids = image_channelids
        self.base_role_id = base_role_id
        self.mention_last = {}
        self.cooldown = 30 * 60
        
        self.bg_task = self.client.loop.create_task(self.background_task())

    async def create_tables(self):
        await self.client.db.execute(
            """
            CREATE TABLE IF NOT EXISTS art_mention (
                userid BIGINT,
                character VARCHAR,
                UNIQUE(userid, character)
            );
            """
        )
        await self.client.db.commit()

    async def background_task(self):
        await self.client.wait_until_ready()
        while not self.client.is_closed():
            for guild in self.client.guilds:
                for role in list(guild.roles):
                    if role.name.endswith(" - Fanart Notification"):
                        try:
                            await role.delete()
                        except:
                            pass
            await asyncio.sleep(86400) # 1 day

    async def on_message(self, message):
        if message.author.id == self.client.user.id or len(message.content) == 0:
            return
        if message.content.startswith(self.client.cmd_prefix + "subscribe"):
            await self.cmd_subscribe(message)
        elif message.content.startswith(self.client.cmd_prefix + "unsubscribe"):
            await self.cmd_unsubscribe(message)
        elif message.content.startswith(self.client.cmd_prefix + "listsubs"):
            await self.cmd_listsubs(message)
        if message.channel.id not in self.image_channelids:
            return
        content_split = message.content.lower().split()
        roles_to_mention = set()
        for character, subscribed_users in (await self.get_all_subscriptions()).items():
            character = character.lower()
            if "!!{}".format(character) not in content_split:
                continue
            if self.get_cooldown_seconds(character) > 0:
                continue
            self.mention_last[character] = datetime.datetime.now()
            role = await self.get_role(character, message.guild)
            if not role:
                continue
            roles_to_mention.add(role)
        if len(roles_to_mention):
            mentions = ""
            for role in roles_to_mention:
                mentions = mentions + role.mention + " "
            mention_msg = "{}: {}".format(message.author.mention, mentions)
            await message.channel.send(mention_msg)

    async def get_role(self, character, guild):
        if not guild:
            return None
        subscriptions = await self.get_all_subscriptions()
        character = character.lower()
        if character not in subscriptions:
            return None
        users = []
        for userid in subscriptions[character]:
            member = guild.get_member(userid)
            if not member:
                continue
            users.append(member)
        if len(users) == 0:
            return None
        base_role = guild.get_role(self.base_role_id)
        if not base_role:
            return None
        role = None
        role_name = "{} - Fanart Notification".format(character)
        for server_role in guild.roles:
            if server_role.name == role_name:
                role = server_role
                break
        if not role:
            role = await guild.create_role(name=role_name)
            await guild.edit_role_positions({role: base_role.position - 1})
        for member in list(role.members):
            if member not in users:
                await member.remove_roles(role)
        for user in users:
            if user not in role.members:
                await member.add_roles(role)
        return role

    async def cmd_subscribe(self, message):
        content_split = message.content.lower().split()
        if len(content_split) == 1:
            await message.channel.send("Please specify all the fanart notifications you would like to subscribe. Seperate multiple ones by a space.")
            return
        existing = await self.get_all_user_subscriptions(message.author.id)
        success = []
        fail_already_subbed = []
        fail_illegal_format = []
        characters = set(content_split[1:])
        for character in characters:
            character = character.lower()
            if character in existing:
                fail_already_subbed.append(character)
                continue
            if not character.isalnum():
                fail_illegal_format.append(character)
                continue
            await self.subscribe_user(message.author.id, character)
            success.append(character)
        result = "{} ".format(message.author.mention)
        if len(success):
            result = result + "Successfully subscribed to **{}**. To view your current subscriptions, use `!listsubs`.\n".format(", ".join(success))
        if len(fail_already_subbed):
            result = result + "You have already subscribed to **{}**.\n".format(", ".join(fail_already_subbed))
        if len(fail_illegal_format):
            result = result + "Unable to subscribe to **{}**. Names must only contain letter and numbers.".format(", ".join(fail_illegal_format))
        await message.channel.send(result)

    async def cmd_unsubscribe(self, message):
        content_split = message.content.lower().split()
        if len(content_split) == 1:
            await message.channel.send("Please specify all the fanart notifications you would like to unsubscribe. Seperate multiple ones by a space.")
            return
        existing = await self.get_all_user_subscriptions(message.author.id)
        success = []
        failed_not_subbed = []
        characters = set(content_spit[1:])
        for character in characters:
            character = character.lower()
            if character not in existing:
                failed_not_subbed.append(character)
                continue
            await self.unsubscribe_user(message.author.id, character)
            success.append(character)
        result = "{} ".format(message.author.mention)
        if len(success):
            result = result + "Successfully unsubscribed to {}. To view your current subscriptions, use `!listsubs`.\n".format(", ".join(success))
        if len(failed_not_subbed):
            result = result + "You have not subscribed to {}.".format(", ".join(failed_not_subbed))
        await message.channel.send(result)

    async def cmd_listsubs(self, message):
        content_split = message.content.split()
        if len(content_split) == 1:
            subs = await self.get_all_user_subscriptions(message.author.id)
            await message.channel.send("{}'s subscription: {}".format(message.author.mention, ", ".join(subs)))
            return
        subs = await self.get_all_subscriptions()
        if "#" in content_split:
            count = []
            for character, users in subs.items():
                count.append("**{}** ({})".format(character, len(users)))
            await message.channel.send("List of all subscriptions: {}".format(", ".join(count)))
        result = ""
        for mention in message.mentions:
            user_subs = await self.get_all_user_subscriptions(mention.id)
            result = result + "{}'s subscription: {}\n".format(mention.mention, ", ".join(user_subs))
        if result:
            await message.channel.send(result, allowed_mentions=discord.AllowedMentions.none())
        result = ""
        for character in content_split[1:]:
            character = character.lower()
            if not character.startswith("<") and character != "#":
                users = subs.get(character, [])
                members = []
                for user_id in users:
                    user = self.client.get_user(user_id)
                    if user:
                        members.append(user.mention)
                result = result + "Members who subscribed to **{}** ({}): {}\n".format(character, len(members), ", ".join(members))
        if result:
            await message.channel.send(result, allowed_mentions=discord.AllowedMentions.none())

    async def get_all_subscriptions(self):
        cursor = await self.client.db.execute("SELECT userid, character FROM art_mention ORDER BY character;")
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            uid = row[0]
            char = row[1]
            if char not in result:
                result[char] = []
            result[char].append(uid)
        return result

    async def get_all_user_subscriptions(self, user_id):
        subscriptions = await self.get_all_subscriptions()
        result = []
        for character, users in subscriptions.items():
            if user_id in users:
                result.append(character)
        return result

    async def subscribe_user(self, user_id, character):
        await self.client.db.execute(
            "INSERT INTO art_mention (userid, character) VALUES (?, ?);",
            (user_id, character)
        )
        await self.client.db.commit()

    async def unsubscribe_user(self, user_id, character):
        await self.client.db.execute(
            "DELETE FROM art_mention WHERE userid = ? AND character = ?;",
            (user_id, character)
        )
        await self.client.db.commit()

    def get_cooldown_seconds(self, name):
        if name not in self.mention_last:
            return 0
        elapsed_last = (datetime.datetime.now() - self.mention_last[name]).total_seconds()
        time_left = max(self.cooldown - elapsed_last, 0)
        return round(time_left)