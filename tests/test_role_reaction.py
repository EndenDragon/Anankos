import unittest
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Anankos.role_reaction import RoleReaction


def make_role_reaction(role_reaction_config=None, permanent_roles=None):
    client = MagicMock()
    return RoleReaction(
        client,
        role_reaction=role_reaction_config or {},
        permanent_roles=permanent_roles or {}
    )


def make_payload(message_id, user_id, channel_id, emoji_id, emoji_name):
    payload = MagicMock()
    payload.message_id = message_id
    payload.user_id = user_id
    payload.channel_id = channel_id
    emoji = MagicMock()
    emoji.id = emoji_id
    emoji.name = emoji_name
    payload.emoji = emoji
    return payload


class TestEmojiCheck(unittest.IsolatedAsyncioTestCase):
    async def test_unicode_emoji_uses_name(self):
        role_id = 555
        rr = make_role_reaction(
            role_reaction_config={100: {"🎭": role_id}},
        )
        payload = make_payload(message_id=100, user_id=1, channel_id=10, emoji_id=None, emoji_name="🎭")

        channel = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.id = 1
        role = MagicMock()
        role.id = role_id

        guild.get_member = MagicMock(return_value=member)
        guild.get_role = MagicMock(return_value=role)
        channel.guild = guild
        rr.client.get_channel = MagicMock(return_value=channel)

        result_member, result_role = await rr.get_member_and_role(payload)
        self.assertEqual(result_member, member)
        self.assertEqual(result_role, role)

    async def test_custom_emoji_uses_id(self):
        emoji_id = 98765
        role_id = 444
        rr = make_role_reaction(
            role_reaction_config={100: {emoji_id: role_id}},
        )
        payload = make_payload(message_id=100, user_id=1, channel_id=10, emoji_id=emoji_id, emoji_name="custom")

        channel = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.id = 1
        role = MagicMock()
        role.id = role_id

        guild.get_member = MagicMock(return_value=member)
        guild.get_role = MagicMock(return_value=role)
        channel.guild = guild
        rr.client.get_channel = MagicMock(return_value=channel)

        result_member, result_role = await rr.get_member_and_role(payload)
        self.assertEqual(result_member, member)
        self.assertEqual(result_role, role)

    async def test_wrong_message_id_returns_none(self):
        rr = make_role_reaction(role_reaction_config={999: {"🎭": 555}})
        payload = make_payload(message_id=100, user_id=1, channel_id=10, emoji_id=None, emoji_name="🎭")
        result = await rr.get_member_and_role(payload)
        self.assertEqual(result, (None, None))

    async def test_emoji_not_in_config_returns_none(self):
        rr = make_role_reaction(role_reaction_config={100: {"🎭": 555}})
        payload = make_payload(message_id=100, user_id=1, channel_id=10, emoji_id=None, emoji_name="🎉")

        channel = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.id = 1
        guild.get_member = MagicMock(return_value=member)
        channel.guild = guild
        rr.client.get_channel = MagicMock(return_value=channel)

        result = await rr.get_member_and_role(payload)
        self.assertEqual(result, (None, None))

    async def test_permanent_role_skipped(self):
        role_id = 555
        user_id = 1
        rr = make_role_reaction(
            role_reaction_config={100: {"🎭": role_id}},
            permanent_roles={user_id: [role_id]},
        )
        payload = make_payload(message_id=100, user_id=user_id, channel_id=10, emoji_id=None, emoji_name="🎭")

        channel = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.id = user_id
        role = MagicMock()
        role.id = role_id

        guild.get_member = MagicMock(return_value=member)
        guild.get_role = MagicMock(return_value=role)
        channel.guild = guild
        rr.client.get_channel = MagicMock(return_value=channel)

        result = await rr.get_member_and_role(payload)
        self.assertEqual(result, (None, None))

    async def test_reaction_add_calls_add_roles(self):
        role_id = 555
        rr = make_role_reaction(role_reaction_config={100: {"🎭": role_id}})
        payload = make_payload(message_id=100, user_id=1, channel_id=10, emoji_id=None, emoji_name="🎭")

        member = MagicMock()
        member.id = 1
        member.add_roles = AsyncMock()
        role = MagicMock()
        role.id = role_id

        channel = MagicMock()
        guild = MagicMock()
        guild.get_member = MagicMock(return_value=member)
        guild.get_role = MagicMock(return_value=role)
        channel.guild = guild
        rr.client.get_channel = MagicMock(return_value=channel)

        await rr.on_raw_reaction_add(payload)
        member.add_roles.assert_called_once_with(role)

    async def test_reaction_remove_calls_remove_roles(self):
        role_id = 555
        rr = make_role_reaction(role_reaction_config={100: {"🎭": role_id}})
        payload = make_payload(message_id=100, user_id=1, channel_id=10, emoji_id=None, emoji_name="🎭")

        member = MagicMock()
        member.id = 1
        member.remove_roles = AsyncMock()
        role = MagicMock()
        role.id = role_id

        channel = MagicMock()
        guild = MagicMock()
        guild.get_member = MagicMock(return_value=member)
        guild.get_role = MagicMock(return_value=role)
        channel.guild = guild
        rr.client.get_channel = MagicMock(return_value=channel)

        await rr.on_raw_reaction_remove(payload)
        member.remove_roles.assert_called_once_with(role)


if __name__ == "__main__":
    unittest.main()
