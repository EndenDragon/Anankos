from Anankos.bot import Anankos
from config import CONFIG

anankos = Anankos(CONFIG)
anankos.run(CONFIG["bot_token"])
