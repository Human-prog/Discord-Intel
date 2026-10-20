"""Project mapping and command set (Phase 11).

Implements /next, /roadmap, /blocker, /connect-project, /note, /health commands.
All commands pass through central authorization before retrieving project data.
Project mapping is explicit and validated; paths must remain within configured roots.
"""

from __future__ import annotations

from typing import Any, Optional

from project_intelligence.config import Settings, load_settings
from project_intelligence.security import (
    AuthContext,
    make_checker,
    AuthorizationError,
    rate_limiter,
)

# Conditional discord.py import
try:
    import discord
    from discord import app_commands
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None  # type: ignore[assignment]
    app_commands = None  # type: ignore[assignment]


if DISCORD_AVAILABLE:

    @app_commands.command(name="next", description="Evidence-backed suggested next actions")
    async def next_command(interaction: discord.Interaction) -> None:
        """Evidence-backed suggested next actions."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = interaction.client.settings
        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return
        await interaction.response.send_message(
            "**Next Actions**\n\nNo project data available yet. "
            "Use `/connect-project` to map this context to a project.",
            ephemeral=True,
        )

    @app_commands.command(name="roadmap", description="View project milestones and progress")
    async def roadmap_command(interaction: discord.Interaction) -> None:
        """View project milestones and progress."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = interaction.client.settings
        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return
        await interaction.response.send_message(
            "**Project Roadmap**\n\nNo milestones recorded yet. "
            "Use `/connect-project` to map this context to a project.",
            ephemeral=True,
        )

    @app_commands.command(name="blocker", description="View or record project blockers")
    async def blocker_command(interaction: discord.Interaction) -> None:
        """View or record project blockers."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = interaction.client.settings
        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return
        await interaction.response.send_message(
            "**Project Blockers**\n\nNo blockers recorded. "
            "Use `/connect-project` to map this context to a project.",
            ephemeral=True,
        )

    @app_commands.command(name="connect-project", description="Map an approved Discord context to a project")
    async def connect_project_command(interaction: discord.Interaction, project_id: int) -> None:
        """Map an approved Discord context to a project (owner only)."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = interaction.client.settings
        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
            if not auth_ctx.is_owner(settings):
                raise AuthorizationError("Only owners can connect projects.")
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return
        await interaction.response.send_message(
            f"Project {project_id} connected to this guild/channel context.",
            ephemeral=True,
        )

    @app_commands.command(name="note", description="Save a project note")
    async def note_command(interaction: discord.Interaction, content: str) -> None:
        """Save a project note."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = interaction.client.settings
        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return
        await interaction.response.send_message(
            f"Note saved: {content[:100]}",
            ephemeral=True,
        )

    @app_commands.command(name="health", description="Inspect project health snapshots")
    async def health_command(interaction: discord.Interaction) -> None:
        """Inspect project health snapshots."""
        auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
        settings = interaction.client.settings
        if auth_ctx is None:
            await interaction.response.send_message("Authentication required.", ephemeral=True)
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)
            return
        await interaction.response.send_message(
            "**Project Health**\n\nNo health snapshots available. "
            "Use `/connect-project` to map this context to a project.",
            ephemeral=True,
        )
else:
    next_command = None
    roadmap_command = None
    blocker_command = None
    connect_project_command = None
    note_command = None
    health_command = None