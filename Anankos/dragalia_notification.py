import datetime
import aiohttp
import asyncio
import html

class DragaliaNotification:
    def __init__(self, client, channel_id, role_id):
        self.client = client
        self.channel_id = channel_id
        self.role_id = role_id
        self.httpsession = aiohttp.ClientSession()

        self.bg_task = self.client.loop.create_task(self.background_task())

    async def background_task(self):
        await self.client.wait_until_ready()
        while not self.client.is_closed():
            utc = datetime.datetime.utcnow()
            if utc.hour == 6 and utc.minute == 0:
                await self.run_reminders()
                await asyncio.sleep(120)
            await asyncio.sleep(30)

    async def cargo_query(self, *, limit=10, tables=None, fields=None, where=None, order_by=None):
        url = "https://dragalialost.wiki/api.php"
        params = {
            "action": "cargoquery",
            "format": "json"
        }
        if limit:
            params["limit"] = limit
        if tables:
            params["tables"] = tables
        if fields:
            params["fields"] = fields
        if where:
            params["where"] = where
        if order_by:
            params["order_by"] = order_by
        async with self.httpsession.get(url, params=params) as resp:
            if resp.status < 200 or resp.status >= 300:
                return []
            return (await resp.json())["cargoquery"]
        return []

    async def run_reminders(self):
        summon_showcases = await self.cargo_query(
            tables = "SummonShowcase",
            fields = "Title,EndDate",
            where = "EndDate < DATE_ADD(NOW(), INTERVAL 1 DAY) AND EndDate > NOW()",
            order_by = "EndDate DESC"
        )
        events = await self.cargo_query(
            tables = "Events",
            fields = "Name,EndDate",
            where = "EndDate < DATE_ADD(NOW(), INTERVAL 1 DAY) AND EndDate > NOW()",
            order_by = "EndDate DESC"
        )
        secondary_events = await self.cargo_query(
            limit = 20,
            tables = "SecondaryEvents",
            fields = "Name,StartDate",
            where = "StartDate > DATE_SUB(NOW(), INTERVAL 1 HOUR) AND StartDate < NOW()",
            order_by = "StartDate DESC"
        )
        should_post = False
        output = "**Dragalia Schedule Notification** <@&{}>".format(self.role_id)
        if len(summon_showcases):
            should_post = True
            output = output + "\n__Summon Showcases (ending today):__"
            for summon in summon_showcases:
                output = output + "\n{}".format(html.unescape(summon["title"]["Title"]))
            output = output + "\n"
        if len(events):
            should_post = True
            output = output + "\n__Limited Events (ending today):__"
            for event in events:
                output = output + "\n{}".format(html.unescape(event["title"]["Name"]))
            output = output + "\n"
        if len(secondary_events):
            secondary_should_post = False
            secondary_events_output = "\n__Other Events (starts today):__"
            for event in secondary_events:
                name = html.unescape(event["title"]["Name"])
                if not self.include_secondary_event(name):
                    continue
                secondary_should_post = True
                secondary_events_output = secondary_events_output + "\n{}".format(name)
            secondary_events_output = secondary_events_output + "\n"
            if secondary_should_post:
                output = output + secondary_events_output
                should_post = True
        if should_post:
            channel = self.client.get_channel(self.channel_id)
            webhooks = await channel.webhooks()
            if len(webhooks):
                webhook = webhooks[0]
                await webhook.send(output)

    def include_secondary_event(self, name):
        name = name.lower()
        # summon
        if "free" in name and "summon" in name:
            return True
        # agito
        if ("agito" in name or "volk" in name or "kai" in name or "ciella" in name or "otoha" in name or "tartarus" in name) \
                and ("double" in name or "half" in name or "triple" in name):
            return True
        # dominion
        if ("dominion" in name or "lilith" in name or "jalda" in name or "asura" in name) \
                and ("double" in name or "half" in name or "triple" in name):
            return True
        # campaign
        if "campaign" in name and ("double" in name or "half" in name or "triple" in name):
            return True
        # Advanced Dragon Trials
        if "advanced" in name and "dragon" in name and ("double" in name or "half" in name or "triple" in name):
            return True
        # Maintenance
        if "maintenance" in name:
            return True
        # void
        if "void" in name and ("double" in name or "half" in name or "triple" in name):
            return True
        return False