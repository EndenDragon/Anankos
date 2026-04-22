from Anankos.pick_a_number import PickANumber
from Anankos.role_reaction import RoleReaction
from Anankos.bad_words import BadWords
from Anankos.permanent_roles import PermanentRoles
from Anankos.trivia import Trivia
from Anankos.image_embed import ImageEmbed
from Anankos.reddit_publish import RedditPublish
from Anankos.looking_for_smash import LookingForSmash
from Anankos.mass_corrin_ping import MassCorrinPing
from Anankos.art_mention import ArtMention, ArtMentionButton
from Anankos.nitro_emote import NitroEmote
from Anankos.dragalia_notification import DragaliaNotification
from Anankos.activities import Activities
from Anankos.priconne_notification import PriconneNotification
from Anankos.automod import AutoMod
from Anankos.art_deduper import ArtDeduper
from Anankos.edit_link_filter import EditLinkFilter
from Anankos.poll_manager import PollManager

import asyncio
import discord
import aiosqlite
import sqlite3
from discord.ext import commands

class Anankos(commands.Bot):
    def __init__(self, config):
        super().__init__(
            command_prefix=config.get("cmd_prefix", "!"),
            activity=discord.Game(name=config.get("playing_status", "with Dragon Veins")),
            intents=discord.Intents.all()
        )
        self.config = config
        self.db = None
        self.cmd_prefix = config.get("cmd_prefix", "!")
        self.bad_words = BadWords(self, config.get("bad_words", []))
        self.pick_a_number = PickANumber(self, config.get("PaN_enabled", False), config.get("PaN_channel", 0), config.get("PaN_eventid", "default"), config.get("PaN_cooldown", 60))
        self.role_reaction = RoleReaction(self, config.get("role_reaction", {}), config.get("permanent_roles", {}))
        self.permanent_roles = PermanentRoles(self, config.get("permanent_roles", {}))
        self.trivia = Trivia(self, config.get("Triv_enabled", False), config.get("Triv_channel", 0), config.get("Triv_eventid", "default"), config.get("Triv_role_pingerid", 0), config.get("Triv_cooldown_min", 30), config.get("Triv_cooldown_max", 45))
        self.image_embed = ImageEmbed(self, config.get("imageembed_channelids", []))
        self.reddit_publish = RedditPublish(self, config.get("redditpub_source_chan_id"), config.get("redditpub_dest_chan_id"), config.get("redditpub_clientid"), config.get("redditpub_clientsecret"))
        self.looking_for_smash = LookingForSmash(self, config.get("lfs_channelid"), config.get("lfs_roleid"))
        self.mass_corrin_ping = MassCorrinPing(self)
        self.art_mention = ArtMention(self, config.get("artmention_channelids", []), config.get("artmention_thread_channelids", []), config.get("artmention_base_role_id", 0), config.get("artmention_pingboard_channelid", 0))
        self.nitro_emote = NitroEmote(self)
        self.dragalia_notification = DragaliaNotification(self, config.get("dragalianotif_channelid"), config.get("dragalianotif_roleid"))
        self.activities = Activities(self, config.get("activities_channelid"))
        self.priconne_notification = PriconneNotification(self, config.get("priconnenotif_channelid"))
        self.automod = AutoMod(self)
        self.art_deduper = ArtDeduper(self, config.get("deduper_channelids", []))
        self.edit_link_filter = EditLinkFilter(self, config.get("elf_links", []))
        self.poll_manager = PollManager(self, config.get("poll_channelid"))

    async def setup_hook(self):
        self.db = await aiosqlite.connect("db.sqlite3", detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        await self.pick_a_number.create_tables()
        await self.trivia.create_tables()
        await self.art_mention.create_tables()

        self.add_dynamic_items(ArtMentionButton)

        self.trivia.start_tasks()
        self.art_mention.start_tasks()
        self.dragalia_notification.start_tasks()
        self.reddit_publish.start_tasks()
        self.priconne_notification.start_tasks()
        self.image_embed.start_sessions()

    async def on_ready(self):
        print("[Anankos by EndenDragon]")
        print("For Corrin Conclave -- https://Corr.in/")
        print(self.user.name)
        print(self.user.id)
        print('------')

    async def on_message(self, message):
        asyncio.create_task(self.pick_a_number.on_message(message))
        asyncio.create_task(self.bad_words.on_message(message))
        asyncio.create_task(self.trivia.on_message(message))
        asyncio.create_task(self.reddit_publish.on_message(message))
        asyncio.create_task(self.looking_for_smash.on_message(message))
        asyncio.create_task(self.mass_corrin_ping.on_message(message))
        asyncio.create_task(self.art_mention.on_message(message))
        asyncio.create_task(self.image_embed.on_message(message))
        asyncio.create_task(self.nitro_emote.on_message(message))
        asyncio.create_task(self.activities.on_message(message))
        asyncio.create_task(self.automod.on_message(message))
        asyncio.create_task(self.art_deduper.on_message(message))
        asyncio.create_task(self.poll_manager.on_message(message))

    async def on_message_edit(self, before, after):
        await self.bad_words.on_message_edit(before, after)
        await self.edit_link_filter.on_message_edit(before, after)
        await self.image_embed.on_message_edit(before, after)

    async def on_raw_reaction_add(self, payload):
        await self.role_reaction.on_raw_reaction_add(payload)
        await self.reddit_publish.on_raw_reaction_add(payload)

    async def on_raw_reaction_remove(self, payload):
        await self.role_reaction.on_raw_reaction_remove(payload)

    async def on_member_join(self, member):
        await self.permanent_roles.on_member_join(member)

    async def on_message_delete(self, message):
        await self.image_embed.on_message_delete(message)
        await self.art_deduper.on_message_delete(message)

    async def close(self):
        closers = [
            self.dragalia_notification.close(),
            self.image_embed.close(),
            self.reddit_publish.close(),
            self.priconne_notification.close(),
        ]
        await asyncio.gather(*closers, return_exceptions=True)
        if self.db:
            try:
                await self.db.close()
            except Exception:
                pass
        await super().close()
