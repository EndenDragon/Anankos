import datetime
import discord
import asyncio
import re

class ArtMention:
    def __init__(self, client, image_channelids, base_role_id):
        self.client = client
        self.image_channelids = image_channelids
        self.base_role_id = base_role_id
        self.mention_last = {}
        self.cooldown = 30 * 60
        self.re_compiled = {}
        
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
        await self.client.db.execute(
            """
            CREATE TABLE IF NOT EXISTS art_mention_timestamp (
                character VARCHAR,
                timestamp TIMESTAMP,
                UNIQUE(character)
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
                        character = role.name.split()[0]
                        if await self.role_expired(character):
                            try:
                                await role.delete()
                            except:
                                pass
            await asyncio.sleep(43200) # 12 hours

    async def role_expired(self, character):
        elapsed_last = await self.get_time_elapsed(character)
        if elapsed_last < 0:
            return True
        time_left = max(172800 - elapsed_last, 0) # 2 days
        return time_left <= 0

    async def get_time_elapsed(self, character):
        character = character.lower()
        cursor = await self.client.db.execute("SELECT timestamp FROM art_mention_timestamp WHERE character = ? LIMIT 1;", (character, ))
        row = await cursor.fetchone()
        if row is None:
            return -1
        timestamp = row[0]
        elapsed_last = (datetime.datetime.now() - timestamp).total_seconds()
        return elapsed_last

    async def bump_character(self, character):
        character = character.lower()
        time = datetime.datetime.now()
        cursor = await self.client.db.execute("SELECT timestamp FROM art_mention_timestamp WHERE character = ? LIMIT 1;", (character, ))
        row = await cursor.fetchone()
        if row is None:
            await self.client.db.execute("INSERT INTO art_mention_timestamp (character, timestamp) VALUES (?, ?);", (character, time))
        else:
            await self.client.db.execute("UPDATE art_mention_timestamp SET timestamp = ? WHERE character = ?;", (time, character))
        await self.client.db.commit()

    async def on_message(self, message):
        if message.author.id == self.client.user.id or len(message.content) == 0:
            return
        if message.content.startswith(self.client.cmd_prefix + "subscribe"):
            await self.cmd_subscribe(message)
        elif message.content.startswith(self.client.cmd_prefix + "unsubscribe"):
            await self.cmd_unsubscribe(message)
        elif message.content.startswith(self.client.cmd_prefix + "listsubs"):
            await self.cmd_listsubs(message)
        elif message.content.startswith(self.client.cmd_prefix + "streak"):
            await self.cmd_streak(message)
        if message.channel.id not in self.image_channelids:
            return
        content_split = message.content.lower().split()
        roles_to_mention = set()
        for character, subscribed_users in (await self.get_all_subscriptions()).items():
            character = character.lower()
            compiled = self.re_compiled.get(character, None)
            if compiled is None:
                compiled = re.compile("^!!{}\W*$".format(character))
                self.re_compiled[character] = compiled
            matches_character = False
            if not any(compiled.match(token) for token in content_split):
                continue
            if self.get_cooldown_seconds(character) > 0:
                continue
            self.mention_last[character] = datetime.datetime.now()
            await self.add_wait_emote(message)
            role = await self.get_role(character, message.guild)
            if not role:
                continue
            roles_to_mention.add(role)
            await self.bump_character(character)
        await self.remove_wait_emote(message)
        #roles_to_mention = list(roles_to_mention)[:9]
        if len(roles_to_mention):
            mentions = ""
            for role in roles_to_mention:
                mentions = mentions + role.mention + " "
            await message.reply(mentions, mention_author=False)

    async def add_wait_emote(self, message):
        for reaction in message.reactions:
            if str(reaction.emoji) == "⌛" and reaction.me:
                return
        await message.add_reaction("⌛")

    async def remove_wait_emote(self, message):
        message = await message.channel.fetch_message(message.id)
        for reaction in message.reactions:
            if str(reaction.emoji) == "⌛" and reaction.me:
                await message.remove_reaction("⌛", self.client.user)

    async def get_role(self, character, guild, create_role=True):
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
        if create_role:
            if not role:
                role = await guild.create_role(name=role_name)
                await guild.edit_role_positions({role: base_role.position - 1})
            for member in list(role.members):
                if member not in users:
                    await member.remove_roles(role)
            for user in users:
                if user not in role.members:
                    await user.add_roles(role)
        return role

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

    async def cmd_streak(self, message):
        streaks = []
        subs = await self.get_all_subscriptions()
        time_diff = (datetime.datetime.now() - datetime.datetime.utcnow()).total_seconds()
        for character in subs.keys():
            role = await self.get_role(character, message.guild, False)
            if role:
                elapsed_last = await self.get_time_elapsed(character)
                if elapsed_last < 0:
                    continue
                last_posted = datetime.datetime.now() - datetime.timedelta(seconds=elapsed_last)
                role_created = role.created_at + datetime.timedelta(seconds=time_diff)
                elapsed = (last_posted - role_created).total_seconds()
                streaks.append((character, elapsed))
        streaks = sorted(streaks, key = lambda x: x[1], reverse=True)
        output = "**Fanart Notification Streaks**\nNotification roles are removed when they have not been used in a while. These characters have been used recently and held their role for this long since it was made until the last time it was used."
        for streak in streaks:
            character = streak[0]
            elapsed = self.format_cooldown(streak[1])
            output = output + "\n{}, {}".format(character, elapsed)
        if len(streaks) == 0:
            output = output + "\n(there are none)"
        await message.channel.send(output)

    async def cmd_subscribe(self, message):
        content_split = message.content.lower().split()
        if len(content_split) == 1:
            await self.respond(message, "Please specify all the fanart notifications you would like to subscribe. Seperate multiple ones by a space.", "✅")
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
            success.append("{} ({})".format(character, await self.get_sub_count(character)))
        result = "{} ".format(message.author.mention)
        if len(success):
            result = result + "Successfully subscribed to **{}**. To view your current subscriptions, use `!listsubs`.\n".format(", ".join(success))
            emoji = "✅"
        if len(fail_already_subbed):
            result = result + "You have already subscribed to **{}**.\n".format(", ".join(fail_already_subbed))
            emoji = "❌"
        if len(fail_illegal_format):
            result = result + "Unable to subscribe to **{}**. Names must only contain letter and numbers.".format(", ".join(fail_illegal_format))
            emoji = "❌"
        await self.respond(message, result, emoji)

    async def respond(self, message, contents, emoji):
        msg = await message.channel.send(contents)
        if message.channel.id in self.image_channelids:
            await message.add_reaction(emoji)
            await asyncio.sleep(15)
            await msg.delete()

    async def cmd_unsubscribe(self, message):
        content_split = message.content.lower().split()
        if len(content_split) == 1:
            await message.channel.send("Please specify all the fanart notifications you would like to unsubscribe. Seperate multiple ones by a space.")
            return
        existing = await self.get_all_user_subscriptions(message.author.id)
        success = []
        failed_not_subbed = []
        characters = set(content_split[1:])
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
            result = "List of all subscriptions: {}".format(", ".join(count))
            lines = result.splitlines()
            for line in lines:
                output = ""
                tokens = line.split()
                for token in tokens:
                    output = output + token + " "
                    if len(output) > 1900:
                        await message.channel.send(output, allowed_mentions=discord.AllowedMentions.none())
                        output = ""
                if output:
                    await message.channel.send(output, allowed_mentions=discord.AllowedMentions.none())
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

    async def get_sub_count(self, character):
        subs = (await self.get_all_subscriptions()).get(character)
        count = 0
        for user in subs:
            user = self.client.get_user(user)
            if user:
                count = count + 1
        return count


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
