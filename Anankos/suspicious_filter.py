import datetime
import re


_MENTION_RE = re.compile(r'^<@!?(\d+)>$')
_MIN_ID_DIGITS = 15  # shorter digit strings are treated as usernames, not snowflakes

_KICK_DM = (
    "**You have been kicked from the Corrin Conclave Discord Server because your account appears suspicious.**\n"
    "For appeal, please contact endendragon on Discord or message the r/CorrinConclave subreddit mods. "
    "Please present this message for context when appealing."
)

_TRACK_WINDOW = 300  # seconds to keep newly-joined members in the reaction tracking window
_REACTION_SECS = 60  # react within this many seconds of joining → suspicious (+25 pts)
_MAX_IGNORE_DAYS = 4  # longest a username may be exempted from the filter


class SuspiciousFilter:
    def __init__(self, client, log_channelid, welcome_channelids, kick_score=40):
        self.client = client
        self.log_channelid = log_channelid
        self.welcome_channelids = set(welcome_channelids)
        self.kick_score = kick_score
        self._recently_joined = {}  # user_id -> join datetime
        self._ignored = {}  # key (lowercased username, or digit-string user ID) -> expiry datetime (in-memory only)

    def _prune_ignored(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        for key in [k for k, exp in self._ignored.items() if exp <= now]:
            del self._ignored[key]

    def _normalize_identifier(self, identifier):
        """Returns (key, is_id). A mention (<@id>) or a long digit string is treated as a
        user ID; anything else is treated as a username (case-insensitive)."""
        ident = identifier.strip()
        mention = _MENTION_RE.match(ident)
        if mention:
            return mention.group(1), True
        ident = ident.lstrip("@")
        if ident.isdigit() and len(ident) >= _MIN_ID_DIGITS:
            return ident, True
        return ident.lower(), False

    def add_ignore(self, identifier, days=_MAX_IGNORE_DAYS):
        """Exempts a username or user ID from the filter. Returns (key, expiry, is_id) or None if invalid."""
        key, is_id = self._normalize_identifier(identifier)
        if not key:
            return None
        days = min(max(days, 0), _MAX_IGNORE_DAYS)
        if days <= 0:
            return None
        expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
        self._ignored[key] = expiry
        return key, expiry, is_id

    def remove_ignore(self, identifier):
        """Returns (key, is_id) for the cleared entry, or None if it was not on the list."""
        self._prune_ignored()
        key, is_id = self._normalize_identifier(identifier)
        if key not in self._ignored:
            return None
        del self._ignored[key]
        return key, is_id

    def list_ignored(self):
        """Returns [(key, expiry, is_id)] sorted by soonest expiry."""
        self._prune_ignored()
        return sorted(
            ((key, expiry, key.isdigit() and len(key) >= _MIN_ID_DIGITS) for key, expiry in self._ignored.items()),
            key=lambda item: item[1],
        )

    def is_ignored(self, member):
        self._prune_ignored()
        if str(member.id) in self._ignored:
            return True
        names = [getattr(member, "name", None), getattr(member, "global_name", None)]
        return any(n and n.lower() in self._ignored for n in names)

    def _score(self, member):
        """Returns (total_score, breakdown_list) where each breakdown entry is (label, points)."""
        if member.public_flags.spammer:
            return 100, [("Discord-flagged spammer", 100)]

        breakdown = []
        age_days = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days

        if age_days < 7:
            breakdown.append(("account only {} day(s) old".format(age_days), 50))
        elif age_days < 30:
            breakdown.append(("account only {} days old".format(age_days), 30))
        elif age_days < 60:
            breakdown.append(("account only {} days old".format(age_days), 15))

        if member.avatar is None:
            breakdown.append(("no profile picture", 20))

        if not member.public_flags.value:
            breakdown.append(("no account badges", 10))

        total = sum(pts for _, pts in breakdown)
        return total, breakdown

    def _format_breakdown(self, breakdown, total, threshold):
        parts = ["{} (+{})".format(label, pts) for label, pts in breakdown]
        return "Score: {}/{} | {}".format(total, threshold, ", ".join(parts))

    async def _kick(self, member, score, breakdown):
        reason_str = ", ".join(label for label, _ in breakdown)
        try:
            await member.send(_KICK_DM)
        except Exception:
            pass
        try:
            await member.kick(reason=reason_str)
        except Exception:
            pass
        if self.log_channelid:
            log_channel = self.client.get_channel(self.log_channelid)
            if log_channel:
                await log_channel.send(
                    "**Kicked suspicious user** {} ({})\n{}".format(
                        member.name, member.mention,
                        self._format_breakdown(breakdown, score, self.kick_score)
                    )
                )

    async def on_member_join(self, member):
        """Returns True if the member was kicked so the caller can skip further processing."""
        if member.bot or self.is_ignored(member):
            return False
        score, breakdown = self._score(member)
        if score >= self.kick_score:
            await self._kick(member, score, breakdown)
            return True
        join_time = member.joined_at or datetime.datetime.now(datetime.timezone.utc)
        self._recently_joined[member.id] = join_time
        return False

    async def on_message(self, message):
        if message.author.id == self.client.user.id or len(message.content) == 0:
            return
        prefix = self.client.cmd_prefix
        content = message.content.strip()
        if content.startswith(prefix + "susignore"):
            await self.cmd_susignore(message, content[len(prefix) + len("susignore"):])
        elif content.startswith(prefix + "susunignore"):
            await self.cmd_susunignore(message, content[len(prefix) + len("susunignore"):])
        elif content.startswith(prefix + "suslistignore"):
            await self.cmd_suslistignore(message)

    def _can_manage(self, message):
        """Ignore commands require the Manage Server permission."""
        return message.channel.permissions_for(message.author).manage_guild

    def _display(self, key, is_id):
        """Never renders an actual @mention — an ignored ID may belong to someone in the
        server we don't want to ping just by listing them."""
        return "user ID `{}`".format(key) if is_id else "**{}**".format(key)

    async def cmd_susignore(self, message, args):
        if not self._can_manage(message):
            return
        parts = args.split()
        if not parts:
            await message.channel.send(
                "{} Usage: `{}susignore <username or user ID> [days, max {}]`".format(
                    message.author.mention, self.client.cmd_prefix, _MAX_IGNORE_DAYS
                )
            )
            return
        days = _MAX_IGNORE_DAYS
        if len(parts) > 1:
            try:
                days = float(parts[-1])
                parts = parts[:-1]
            except ValueError:
                pass
        identifier = " ".join(parts)
        result = self.add_ignore(identifier, days)
        if not result:
            await message.channel.send(
                "{} Invalid username, user ID, or duration.".format(message.author.mention)
            )
            return
        key, expiry, is_id = result
        await message.channel.send(
            "{} {} will be ignored by the suspicious filter until <t:{}:f> (<t:{}:R>).".format(
                message.author.mention, self._display(key, is_id), int(expiry.timestamp()), int(expiry.timestamp())
            )
        )

    async def cmd_susunignore(self, message, args):
        if not self._can_manage(message):
            return
        identifier = args.strip()
        if not identifier:
            await message.channel.send(
                "{} Usage: `{}susunignore <username or user ID>`".format(message.author.mention, self.client.cmd_prefix)
            )
            return
        result = self.remove_ignore(identifier)
        if not result:
            key, is_id = self._normalize_identifier(identifier)
            await message.channel.send(
                "{} {} is not on the suspicious filter ignore list.".format(
                    message.author.mention, self._display(key, is_id)
                )
            )
            return
        key, is_id = result
        await message.channel.send(
            "{} {} is no longer ignored by the suspicious filter.".format(
                message.author.mention, self._display(key, is_id)
            )
        )

    async def cmd_suslistignore(self, message):
        if not self._can_manage(message):
            return
        entries = self.list_ignored()
        if not entries:
            await message.channel.send(
                "{} No usernames or user IDs are currently ignored by the suspicious filter.".format(
                    message.author.mention
                )
            )
            return
        lines = [
            "{} — expires <t:{}:R>".format(self._display(key, is_id), int(expiry.timestamp()))
            for key, expiry, is_id in entries
        ]
        await message.channel.send(
            "{} **Suspicious filter ignore list ({}):**\n{}".format(
                message.author.mention, len(entries), "\n".join(lines)
            )
        )

    async def on_raw_reaction_add(self, payload):
        if not self.welcome_channelids or payload.channel_id not in self.welcome_channelids:
            return
        user_id = payload.user_id
        if user_id not in self._recently_joined:
            return

        now = datetime.datetime.now(datetime.timezone.utc)

        # Prune stale entries
        stale = [uid for uid, jt in self._recently_joined.items()
                 if (now - jt).total_seconds() > _TRACK_WINDOW]
        for uid in stale:
            del self._recently_joined[uid]

        if user_id not in self._recently_joined:
            return

        elapsed = (now - self._recently_joined[user_id]).total_seconds()
        if elapsed > _REACTION_SECS:
            return

        guild = self.client.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member or member.bot or self.is_ignored(member):
            return

        score, breakdown = self._score(member)
        reaction_pts = 25
        breakdown.append(("reacted in welcome channel {}s after joining".format(int(elapsed)), reaction_pts))
        score += reaction_pts

        if score >= self.kick_score:
            del self._recently_joined[user_id]
            await self._kick(member, score, breakdown)
