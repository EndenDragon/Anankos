import asyncio
from Anankos.bot import Anankos
from config import CONFIG

async def main():
    async with Anankos(CONFIG) as anankos:
        await anankos.start(CONFIG["bot_token"])

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
