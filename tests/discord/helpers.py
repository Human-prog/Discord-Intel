"""Small Discord interaction doubles for offline command tests."""

from __future__ import annotations

from types import SimpleNamespace

from project_intelligence.security.authentication import AuthContext

# app_settings configures this ID as the owner.
OWNER_ID = 123_456_789_012_345_678
OTHER_USER_ID = 123_456_789_012_345_679
GUILD_ID = 222_222_222_222_222_222
CHANNEL_ID = 333_333_333_333_333_333


class FakeResponse:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send_message(self, message: str, ephemeral: bool = False) -> None:
        self.messages.append((message, ephemeral))


class FakeInteraction:
    """Minimal interaction surface used by the command callbacks."""

    def __init__(
        self,
        settings,
        *,
        user_id: int = OWNER_ID,
        guild_id: int = GUILD_ID,
        channel_id: int = CHANNEL_ID,
        auth_via: str = "discord",
        has_auth: bool = True,
        has_guild: bool = True,
    ) -> None:
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.guild = object() if has_guild else None
        self.channel = object() if has_guild else None
        self.client = SimpleNamespace(settings=settings)
        self.response = FakeResponse()
        self.extras: dict[str, object] = {}
        if has_auth:
            self.extras["auth_ctx"] = AuthContext(
                discord_user_id=user_id,
                discord_guild_id=guild_id,
                discord_channel_id=channel_id,
                auth_via=auth_via,
            )

    @property
    def last_message(self) -> str:
        return self.response.messages[-1][0]

    @property
    def message_count(self) -> int:
        return len(self.response.messages)
