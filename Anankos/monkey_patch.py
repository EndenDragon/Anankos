def monkey_patch():
    from discord_slash import ComponentMessage
    import discord

    class MonkeyMessage(ComponentMessage):
        __slots__ = tuple(list(ComponentMessage.__slots__) + ["poll"])

        def __init__(self, *, state, channel, data):
            super().__init__(state=state, channel=channel, data=data)
            self.poll = data.get("poll")

    def new_override(cls, *args, **kwargs):
        if cls is not MonkeyMessage:
            return object.__new__(MonkeyMessage)
        else:
            return object.__new__(cls)

    discord.message.Message.__new__ = new_override