from Anankos.pick_a_number import PickANumber
import discord
import aiosqlite
import sqlite3

class Anankos(discord.Client):
    def __init__(self, config):
        super().__init__(
            activity=discord.Game(name=config.get("playing_status", "with Dragon Veins"))
        )
        self.config = config
        self.db = None
        self.cmd_prefix = config.get("cmd_prefix", "!")
        self.pick_a_number = PickANumber(self, config.get("PaN_enabled", False), config.get("PaN_channel", 0), config.get("PaN_eventid", "default"), config.get("PaN_cooldown", 60))

    async def on_connect(self):
        if self.db is None:
            self.db = await aiosqlite.connect("db.sqlite3", detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
            await self.pick_a_number.create_tables()

    async def on_ready(self):
        print("[Anankos by EndenDragon#1337]")
        print("For Corrin Conclave -- https://Corr.in/")
        print(self.user.name)
        print(self.user.id)
        print('------')

    async def on_message(self, message):
        await self.pick_a_number.on_message(message)