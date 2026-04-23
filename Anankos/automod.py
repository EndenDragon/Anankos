import re
import datetime
from collections import defaultdict, deque


_BAN_DM = (
    "**You have been banned from the Corrin Conclave Discord Server for the following reason, {}.**\n"
    "For appeal, please contact endendragon on Discord or message the r/CorrinConclave subreddit mods. "
    "Please present this message for context when appealing."
)

_SPAM_WINDOW = 30    # seconds
_SPAM_THRESHOLD = 5  # distinct channels


class AutoMod:
    _URL_RE = re.compile(r'https?://\S+|www\.\S+', re.IGNORECASE)

    def __init__(self, client):
        self.client = client
        self._recent_messages = defaultdict(deque)  # user_id -> deque[(channel_id, content, timestamp)]

    def _normalize(self, content):
        content = self._URL_RE.sub('__url__', content)
        return re.sub(r'\s+', ' ', content.lower().strip())

    async def _ban(self, user, reason):
        try:
            await user.send(_BAN_DM.format(reason))
        except Exception:
            pass
        try:
            await user.ban(reason=reason, delete_message_days=1)
        except Exception:
            pass

    def _check_spam(self, message):
        content = self._normalize(message.content)
        if not content:
            return None

        user_id = message.author.id
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(seconds=_SPAM_WINDOW)
        history = self._recent_messages[user_id]

        while history and history[0][2] < cutoff:
            history.popleft()

        history.append((message.channel.id, content, now))

        channels = {ch for ch, c, _ in history if c == content}
        if len(channels) >= _SPAM_THRESHOLD:
            del self._recent_messages[user_id]
            return "Spamming identical messages across {} channels".format(len(channels))
        return None

    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return

        reason = None
        if ".gift" in message.content:
            reason = "Sent a gift link (probably a Nitro scam from a compromised account)"
        elif len(message.mentions) >= 7:
            reason = "Pinged too many people ({} is way too many)".format(len(message.mentions))
        else:
            reason = self._check_spam(message)

        if reason:
            await self._ban(message.author, reason)
            await message.channel.send("**{} ({}) was banned automatically.**\n{}.".format(
                message.author.name, message.author.mention, reason))
