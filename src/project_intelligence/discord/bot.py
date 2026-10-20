"""Discord Bot Foundation (Phase 10).

Secure Discord application-command foundation using discord.py 2.x.
Implements /help and /status commands with centralized authorization,
ephemeral responses, rate limiting, and offline test mode.

All commands pass through central authorization (Phase 5) before
retrieving any project data.  Bot token loaded from protected config.

When discord.py is not installed, the module is still importable but
DiscordBot and command functions are not available.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from project_intelligence.config import Settings, load_settings
from project_intelligence.security import (
    DEFAULT_RATE_LIMITS,
    AuthError,
    AuthorizationError,
    authenticate_from_interaction,
    make_checker,
    rate_limiter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional discord.py import
# ---------------------------------------------------------------------------

try:
    import discord
    from discord import app_commands
    from discord.ext import commands

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None  # type: ignore[assignment]
    app_commands = None  # type: ignore[assignment]
    commands = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Bot configuration (only when discord.py is available)
# ---------------------------------------------------------------------------

if DISCORD_AVAILABLE:
    INTENTS = discord.Intents.default()
    INTENTS.message_content = False  # No message content scraping

    class DiscordBot(commands.Bot):
        """Discord bot with centralized authorization and minimal intents."""

        def __init__(self, settings: Settings) -> None:
            super().__init__(command_prefix="!", intents=INTENTS)
            self.settings = settings
            self._tree = self.tree

        async def setup_hook(self) -> None:
            """Register guild-scoped commands for development."""
            if self.settings.discord_allowed_guild_ids:
                for guild_id in self.settings.discord_allowed_guild_ids:
                    guild = discord.Object(id=guild_id)
                    self.tree.copy_global_to(guild=guild)
                    await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()

        async def on_ready(self) -> None:
            logger.info("Bot ready as %s", self.user)

        async def on_interaction(self, interaction: discord.Interaction) -> None:
            """Central authorization before command execution."""
            user_id = interaction.user.id if interaction.user else None
            guild_id = interaction.guild_id if interaction.guild else None
            channel_id = interaction.channel_id if interaction.channel else None

            try:
                auth_ctx = authenticate_from_interaction(
                    interaction_user_id=user_id,
                    interaction_guild_id=guild_id,
                    interaction_channel_id=channel_id,
                )
            except AuthError as exc:
                await interaction.response.send_message(
                    f"Authentication failed: {exc.message}", ephemeral=True
                )
                return

            interaction.extras = {"auth_ctx": auth_ctx}
            # discord.py dispatches command callbacks independently; there is
            # no base on_interaction handler to delegate to.

        async def on_command_error(self, ctx: commands.Context[Any], error: Exception) -> None:
            logger.warning("Command error: %s", error)
else:
    DiscordBot = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Command definitions (only when discord.py is available)
# ---------------------------------------------------------------------------

if DISCORD_AVAILABLE:

    @app_commands.command(name="help", description="Show available commands and permissions")
    async def help_command(interaction: discord.Interaction) -> None:
        """Show available commands and permissions."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = cast(Settings, getattr(interaction.client, "settings", None))

        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return

        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return

        limited, reset = rate_limiter.check_command_per_user(auth_ctx.discord_user_id)
        if limited:
            await interaction.response.send_message(
                f"Rate limited. Try again in {int(reset)} seconds.", ephemeral=True
            )
            return

        help_text = """**Discord Project Intelligence - Available Commands**

**General:**
- `/help` - Show this help message
- `/status` - Application and integration status

**Project (authorized users):**
- `/next` - Evidence-backed suggested next actions
- `/roadmap` - View project milestones and progress
- `/blocker` - View or record project blockers
- `/health` - Inspect project health snapshots

**Owner only:**
- `/connect-project` - Map an approved Discord context to a project
- `/note` - Save a project note
- `/research` - Start or retrieve an approved research job
- `/discover` - Discover relevant sources or project opportunities
- `/review` - Review project evidence or research results
- `/report` - Generate an evidence-backed project report

All replies are private (ephemeral) by default.
"""
        await interaction.response.send_message(help_text, ephemeral=True)

    @app_commands.command(name="status", description="Overall application and integration status")
    async def status_command(interaction: discord.Interaction) -> None:
        """Overall application and integration status."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = cast(Settings, getattr(interaction.client, "settings", None))

        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return

        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return

        limited, reset = rate_limiter.check_command_per_user(auth_ctx.discord_user_id)
        if limited:
            await interaction.response.send_message(
                f"Rate limited. Try again in {int(reset)} seconds.", ephemeral=True
            )
            return

        per_user_calls, per_user_window = DEFAULT_RATE_LIMITS["command_per_user"]
        status_text = f"""**Application Status**

**Environment:** {settings.app_env}
**Log level:** {settings.app_log_level}
**Database:** {settings.database_path}
**Dashboard:** {settings.dashboard_bind_host}:{settings.dashboard_bind_port} (loopback only)
**Ollama:** {settings.ollama_base_url} (model: {settings.ollama_model or "unset"})
**GitHub:** {settings.github_mode}
**Research:** {settings.research_provider or "disabled"}
**OpenCode:** {"enabled" if settings.opencode_enabled else "disabled"} (default: disabled)

**Authorization:** Owner IDs: {len(settings.discord_owner_user_ids)} configured
**Rate limits:** {per_user_calls} calls / {per_user_window}s per user
"""
        await interaction.response.send_message(status_text, ephemeral=True)
else:
    help_command = None  # type: ignore[assignment]
    status_command = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Bot factory
# ---------------------------------------------------------------------------


def create_bot(settings: Settings | None = None) -> DiscordBot:
    """Create and configure a DiscordBot instance."""
    if settings is None:
        settings = load_settings()
    if not DISCORD_AVAILABLE:
        raise RuntimeError("discord.py is not installed; cannot create bot")
    bot = DiscordBot(settings)
    bot.tree.add_command(help_command)
    bot.tree.add_command(status_command)
    return bot


# ---------------------------------------------------------------------------
# Offline test mode
# ---------------------------------------------------------------------------


class MockInteraction:
    """Mock Discord interaction for offline testing."""

    def __init__(self, user_id: int, guild_id: int, channel_id: int) -> None:
        self.user = type("User", (), {"id": user_id})()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.response = type(
            "Response",
            (),
            {
                "send_message": lambda self, msg, ephemeral=True: None,
            },
        )()
        self.client = None
        self.extras: dict[str, Any] = {}


def create_test_bot(settings: Settings | None = None) -> DiscordBot:
    """Create a bot for offline testing (no live Discord connection)."""
    if settings is None:
        settings = load_settings(env_file=None)
    if not DISCORD_AVAILABLE:
        raise RuntimeError("discord.py is not installed; cannot create bot")
    return DiscordBot(settings)
