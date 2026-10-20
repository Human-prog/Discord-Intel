"""Offline tests for the Discord bot wiring and command callbacks."""

from __future__ import annotations

import asyncio

from project_intelligence.discord import bot as bot_module
from project_intelligence.discord.commands import project_commands as commands

from .helpers import CHANNEL_ID, GUILD_ID, OWNER_ID, FakeInteraction


def _run(coro):
    return asyncio.run(coro)


def test_create_bot_registers_core_commands(app_settings) -> None:
    bot = bot_module.create_bot(app_settings)

    assert isinstance(bot, bot_module.DiscordBot)
    assert bot.settings is app_settings
    assert bot.tree.get_command("help") is not None
    assert bot.tree.get_command("status") is not None


def test_create_test_bot_needs_no_live_connection(app_settings) -> None:
    bot = bot_module.create_test_bot(app_settings)
    assert isinstance(bot, bot_module.DiscordBot)


def test_on_interaction_attaches_auth_context(app_settings) -> None:
    bot = bot_module.create_test_bot(app_settings)
    interaction = FakeInteraction(app_settings, user_id=OWNER_ID)

    _run(bot.on_interaction(interaction))

    auth_ctx = interaction.extras["auth_ctx"]
    assert auth_ctx.discord_user_id == OWNER_ID
    assert auth_ctx.discord_guild_id == GUILD_ID
    assert auth_ctx.discord_channel_id == CHANNEL_ID


def test_on_interaction_rejects_direct_messages(app_settings) -> None:
    bot = bot_module.create_test_bot(app_settings)
    interaction = FakeInteraction(app_settings, has_guild=False)

    _run(bot.on_interaction(interaction))

    assert interaction.last_message.startswith("Authentication failed")


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
    for name in commands.MAPPED_COMMANDS:
        command = getattr(commands, f"{name.replace('-', '_')}_command")
        assert command is not None
        assert command.name == name
