import datetime


_KICK_DM = (
    "**You have been kicked from the Corrin Conclave Discord Server because your account appears suspicious.**\n"
    "For appeal, please contact endendragon on Discord or message the r/CorrinConclave subreddit mods. "
    "Please present this message for context when appealing."
)

_TRACK_WINDOW = 300  # seconds to keep newly-joined members in the reaction tracking window
_REACTION_SECS = 60  # react within this many seconds of joining → suspicious (+25 pts)


class SuspiciousFilter:
    def __init__(self, client, log_channelid, welcome_channelids, kick_score=40):
        self.client = client
        self.log_channelid = log_channelid
        self.welcome_channelids = set(welcome_channelids)
        self.kick_score = kick_score
        self._recently_joined = {}  # user_id -> join datetime

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
        if member.bot:
            return False
        score, breakdown = self._score(member)
        if score >= self.kick_score:
            await self._kick(member, score, breakdown)
            return True
        join_time = member.joined_at or datetime.datetime.now(datetime.timezone.utc)
        self._recently_joined[member.id] = join_time
        return False

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
        if not member or member.bot:
            return

        score, breakdown = self._score(member)
        reaction_pts = 25
        breakdown.append(("reacted in welcome channel {}s after joining".format(int(elapsed)), reaction_pts))
        score += reaction_pts

        if score >= self.kick_score:
            del self._recently_joined[user_id]
            await self._kick(member, score, breakdown)
