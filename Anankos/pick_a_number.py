import datetime
import io
import csv
import discord

class PickANumber:
    def __init__(self, client, enabled, channel_id, event_id, cooldown):
        self.client = client
        self.enabled = enabled
        self.channel_id = channel_id
        self.event_id = event_id
        self.cooldown = cooldown

    async def create_tables(self):
        await self.client.db.execute(
            """
            CREATE TABLE IF NOT EXISTS pick_a_number (
                eventid VARCHAR,
                userid BIGINT,
                timestamp TIMESTAMP,
                number INT,
                UNIQUE(eventid, number)
            );
            """
        )
        await self.client.db.commit()

    async def on_message(self, message):
        if not self.enabled or message.channel.id != self.channel_id or message.author.id == self.client.user.id:
            return
        if message.content.startswith(self.client.cmd_prefix + "num"):
            await self.cmd_num(message)
        elif message.content.startswith(self.client.cmd_prefix + "cooldown"):
            await self.cmd_cooldown(message)
        elif message.content.startswith(self.client.cmd_prefix + "listnum"):
            await self.cmd_listnum(message)
        elif message.content.startswith(self.client.cmd_prefix + "allnums"):
            await self.cmd_allnums(message)
        elif message.content.startswith(self.client.cmd_prefix + "gennumcsv"):
            await self.cmd_gennumcsv(message)
            
    async def cmd_num(self, message):
        splitted = message.content.split()
        if len(splitted) <= 1 or len(splitted) > 2:
            await message.channel.send("Incorrect parameters! `{}num <1-1000>`".format(self.client.cmd_prefix))
            return
        number = splitted[1]
        if not self.is_int(number):
            await message.channel.send("`{}` is not a number!".format(number))
            return
        number = int(number)
        if number < 1 or number > 1000:
            await message.channel.send("`{}` must be between 1 and 1000!".format(number))
            return
        if await self.number_exists(number):
            await message.channel.send("`{}` has already been claimed. Choose another one!".format(number))
            return
        cooldown = await self.get_cooldown_seconds(message.author.id)
        if cooldown > 0:
            cool_str = self.format_cooldown(cooldown)
            await message.channel.send("Sorry, you gotta wait **{}**!".format(cool_str))
            return
        cursor = await self.client.db.execute(
            "INSERT INTO pick_a_number (eventid, userid, timestamp, number) VALUES (?, ?, ?, ?);",
            (self.event_id, message.author.id, datetime.datetime.now(), number)
        )
        await self.client.db.commit()
        await message.channel.send("**{}** has chosen number **{}**!".format(message.author.mention, number))

    async def cmd_cooldown(self, message):
        cooldown = await self.get_cooldown_seconds(message.author.id)
        if cooldown > 0:
            cool_str = self.format_cooldown(cooldown)
            await message.channel.send("You have to wait **{}** before you can pick an another number!".format(cool_str))
            return
        await message.channel.send("The cooldown for you has expired! Feel free to pick an another number!")

    async def cmd_listnum(self, message):
        user = message.author
        if len(message.mentions):
            user = message.mentions[0]
        numbers = await self.get_user_numbers(user.id)
        if len(numbers):
            result = ", ".join(map(str, numbers))
        else:
            result = "*(You have not chosen any numbers yet)*"
        await message.channel.send("**{}'s numbers**: {}".format(user.mention, result))

    async def cmd_allnums(self, message):
        numbers = await self.get_all_numbers()
        if len(numbers):
            result = ", ".join(map(str, numbers))
        else:
            result = "*(There are no numbers chosen yet)*"
        await message.channel.send("**Here's all the claimed numbers**: {}".format(result))

    async def cmd_gennumcsv(self, message):
        result = await self.get_all_numbers_users()
        f = io.StringIO(newline="")
        csvfile = csv.writer(f)
        csvfile.writerow(["Num", "Name", "User ID"])
        for number, userid in result:
            member = message.guild.get_member(userid)
            name = ""
            if member:
                name = member.name + "#" + member.discriminator
            csvfile.writerow([number, name, userid])
        f.seek(0)
        discordfile = discord.File(f, filename="pick_a_number.csv")
        await message.channel.send("Here is your requested CSV", file=discordfile)

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

    async def number_exists(self, number):
        cursor = await self.client.db.execute("SELECT number FROM pick_a_number WHERE eventid = ? AND number = ?;", (self.event_id, number))
        row = await cursor.fetchall()
        return len(row) > 0

    async def get_cooldown_seconds(self, user_id):
        cursor = await self.client.db.execute("SELECT timestamp FROM pick_a_number WHERE eventid = ? AND userid = ? ORDER BY datetime(timestamp) DESC LIMIT 1;", (self.event_id, user_id))
        row = await cursor.fetchone()
        if row is None:
            return 0
        timestamp = row[0]
        elapsed_last = (datetime.datetime.now() - timestamp).total_seconds()
        time_left = max(self.cooldown - elapsed_last, 0)
        return round(time_left)

    async def get_user_numbers(self, user_id):
        cursor = await self.client.db.execute("SELECT number FROM pick_a_number WHERE eventid = ? AND userid = ? ORDER BY number ASC;", (self.event_id, user_id))
        numbers = []
        rows = await cursor.fetchall()
        for row in rows:
            numbers.append(row[0])
        return numbers
    
    async def get_all_numbers(self):
        numbers = []
        numusrs = await self.get_all_numbers_users()
        for num, user in numusrs:
            numbers.append(num)
        return numbers

    async def get_all_numbers_users(self):
        cursor = await self.client.db.execute("SELECT number, userid FROM pick_a_number WHERE eventid = ? ORDER BY number ASC;", (self.event_id, ))
        result = []
        rows = await cursor.fetchall()
        for row in rows:
            result.append((row[0], row[1]))
        return result

    def is_int(self, num):
        try:
            int(num)
            return True
        except ValueError:
            return False
