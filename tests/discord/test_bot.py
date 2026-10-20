"""Offline tests for the Discord bot wiring and command callbacks."""

from __future__ import annotations

import asyncio

import pytest

from project_intelligence.discord import bot as bot_module
from project_intelligence.discord.commands import project_commands as commands

from .helpers import CHANNEL_ID, GUILD_ID, OWNER_ID, FakeInteraction


def _run(coro):
    return asyncio.run(coro)


def test_create_bot_registers_all_commands(app_settings) -> None:
    bot = bot_module.create_bot(app_settings)

    assert isinstance(bot, bot_module.DiscordBot)
    assert bot.settings is app_settings
    for name in ("help", "status", *commands.MAPPED_COMMANDS, "create-project"):
        assert bot.tree.get_command(name) is not None, name


def test_create_test_bot_needs_no_live_connection(app_settings) -> None:
    bot = bot_module.create_test_bot(app_settings)
    assert isinstance(bot, bot_module.DiscordBot)


def test_interaction_check_attaches_auth_context(app_settings) -> None:
    bot = bot_module.create_test_bot(app_settings)
    interaction = FakeInteraction(app_settings, user_id=OWNER_ID)

    assert _run(bot._interaction_check(interaction)) is True

    auth_ctx = interaction.extras["auth_ctx"]
    assert auth_ctx.discord_user_id == OWNER_ID
    assert auth_ctx.discord_guild_id == GUILD_ID
    assert auth_ctx.discord_channel_id == CHANNEL_ID


def test_interaction_check_rejects_direct_messages(app_settings) -> None:
    bot = bot_module.create_test_bot(app_settings)
    interaction = FakeInteraction(app_settings, has_guild=False)

    assert _run(bot._interaction_check(interaction)) is False

    assert interaction.last_message.startswith("Authentication failed")


def test_setup_hook_syncs_guild_commands(make_settings, monkeypatch) -> None:
    settings = make_settings(discord_allowed_guild_ids=[GUILD_ID])
    bot = bot_module.create_test_bot(settings)
    synced: list[object] = []

    async def fake_sync(*, guild=None):
        synced.append(guild)

    monkeypatch.setattr(bot.tree, "sync", fake_sync)

    _run(bot.setup_hook())

    assert len(synced) == 1
    assert synced[0] is not None


def test_setup_hook_syncs_global_commands_without_guilds(make_settings, monkeypatch) -> None:
    settings = make_settings(discord_allowed_guild_ids=[])
    bot = bot_module.create_test_bot(settings)
    synced: list[object] = []

    async def fake_sync(*, guild=None):
        synced.append(guild)

    monkeypatch.setattr(bot.tree, "sync", fake_sync)

    _run(bot.setup_hook())

    assert synced == [None]


def test_on_ready_and_on_command_error_are_safe(app_settings) -> None:
    bot = bot_module.create_test_bot(app_settings)
    _run(bot.on_ready())
    _run(bot.on_command_error(None, RuntimeError("boom")))


def test_help_lists_commands(app_settings) -> None:
    interaction = FakeInteraction(app_settings)
    _run(bot_module.help_command.callback(interaction))

    assert "Available Commands" in interaction.last_message
    assert "/connect-project" in interaction.last_message
    assert interaction.response.messages[-1][1] is True  # ephemeral


def test_help_requires_authentication(app_settings) -> None:
    interaction = FakeInteraction(app_settings, has_auth=False)
    _run(bot_module.help_command.callback(interaction))
    assert interaction.last_message == "Authentication required."


def test_help_reports_rate_limits(app_settings, monkeypatch) -> None:
    class _Limited:
        @staticmethod
        def check_command_per_user(user_id: int):
            return True, 42.0

    monkeypatch.setattr(bot_module, "rate_limiter", _Limited())
    interaction = FakeInteraction(app_settings)
    _run(bot_module.help_command.callback(interaction))
    assert "Rate limited" in interaction.last_message


def test_status_reports_configuration(app_settings) -> None:
    interaction = FakeInteraction(app_settings)
    _run(bot_module.status_command.callback(interaction))

    message = interaction.last_message
    assert "Application Status" in message
    assert "Environment:** testing" in message
    assert "loopback only" in message
    assert "Rate limits:" in message


def test_status_requires_authentication(app_settings) -> None:
    interaction = FakeInteraction(app_settings, has_auth=False)
    _run(bot_module.status_command.callback(interaction))
    assert interaction.last_message == "Authentication required."


def test_status_reports_rate_limits(app_settings, monkeypatch) -> None:
    class _Limited:
        @staticmethod
        def check_command_per_user(user_id: int):
            return True, 42.0

    monkeypatch.setattr(bot_module, "rate_limiter", _Limited())
    interaction = FakeInteraction(app_settings)
    _run(bot_module.status_command.callback(interaction))
    assert "Rate limited" in interaction.last_message


def test_command_modules_export_all_commands() -> None:
    for name in (*commands.MAPPED_COMMANDS, "create-project"):
        command = getattr(commands, f"{name.replace('-', '_')}_command")
        assert command is not None
        assert command.name == name


# ---------------------------------------------------------------------------
# Runner entrypoint
# ---------------------------------------------------------------------------


def test_main_requires_discord_py(monkeypatch, make_settings) -> None:
    monkeypatch.setattr(bot_module, "DISCORD_AVAILABLE", False)
    monkeypatch.setattr(bot_module, "load_settings", lambda *a, **k: make_settings())

    with pytest.raises(SystemExit, match=r"discord\.py"):
        bot_module.main()


def test_main_refuses_without_a_token(monkeypatch, make_settings) -> None:
    monkeypatch.setattr(bot_module, "load_settings", lambda *a, **k: make_settings())

    with pytest.raises(SystemExit, match="DISCORD_BOT_TOKEN"):
        bot_module.main()


def test_main_runs_the_bot_without_logging_the_token(monkeypatch, make_settings) -> None:
    settings = make_settings(
        discord_bot_token="123456:ABCdef-ghijklmnopqrstuvwxyz",
        discord_owner_user_ids=[OWNER_ID],
    )
    monkeypatch.setattr(bot_module, "load_settings", lambda *a, **k: settings)

    captured: dict[str, object] = {}

    class FakeBot:
        def run(self, token: str, log_handler=None) -> None:
            captured["token"] = token
            captured["log_handler"] = log_handler

    monkeypatch.setattr(bot_module, "create_bot", lambda _settings: FakeBot())

    bot_module.main()

    assert captured["token"] == "123456:ABCdef-ghijklmnopqrstuvwxyz"
    assert captured["log_handler"] is None
