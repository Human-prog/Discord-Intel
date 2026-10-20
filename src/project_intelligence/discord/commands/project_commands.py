"""Project mapping and command set (Phase 11).

Implements /next, /roadmap, /blocker, /connect-project, /note, /health commands.
All commands pass through central authorization before retrieving project data.
Project mapping is explicit and validated; paths must remain within configured roots.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, cast

from project_intelligence.config import Settings
from project_intelligence.health.health_engine import check_and_store_health
from project_intelligence.security import (
    AuthContext,
    AuthorizationError,
    make_checker,
    rate_limiter,
)
from project_intelligence.storage import repositories as repo
from project_intelligence.storage.database import get_conn

# Conditional discord.py import
try:
    import discord
    from discord import app_commands

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None  # type: ignore[assignment]
    app_commands = None  # type: ignore[assignment]


#: Commands registered for a project when an owner runs /connect-project.
MAPPED_COMMANDS: tuple[str, ...] = (
    "next",
    "roadmap",
    "blocker",
    "connect-project",
    "note",
    "health",
)


# ---------------------------------------------------------------------------
# Helpers (independent of discord.py; unit-testable)
# ---------------------------------------------------------------------------


def resolve_project_id(guild_id: int, channel_id: int, command_name: str) -> int | None:
    """Return the project mapped to this guild/channel/command, or None."""
    return repo.get_mapped_project_id(get_conn(), guild_id, channel_id, command_name)


def root_is_allowed(root: str, settings: Settings) -> bool:
    """Fail-closed check that a project root sits under an approved root."""
    try:
        candidate = Path(root).resolve()
    except OSError:
        return False

    if not settings.project_allowed_roots:
        return False

    for allowed in settings.project_allowed_roots:
        try:
            if candidate.is_relative_to(Path(allowed).resolve()):
                return True
        except OSError:
            continue
    return False


def _context(interaction: Any) -> tuple[AuthContext | None, Settings | None]:
    auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
    settings = getattr(getattr(interaction, "client", None), "settings", None)
    return cast(AuthContext | None, auth_ctx), cast(Settings | None, settings)


async def _reply(interaction: Any, message: str) -> None:
    await interaction.response.send_message(message, ephemeral=True)


if DISCORD_AVAILABLE:

    @app_commands.command(name="next", description="Evidence-backed suggested next actions")
    async def next_command(interaction: discord.Interaction) -> None:
        """Evidence-backed suggested next actions."""
        auth_ctx, settings = _context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return

        project_id = resolve_project_id(
            auth_ctx.discord_guild_id, auth_ctx.discord_channel_id, "next"
        )
        if project_id is None:
            await _reply(
                interaction,
                "**Next Actions**\n\nNo project is mapped here. Use `/connect-project` first.",
            )
            return

        await _reply(
            interaction,
            "**Next Actions**\n\nNo suggested actions recorded yet. Suggestions are derived "
            "from repository snapshots and verified evidence.",
        )

    @app_commands.command(name="roadmap", description="View project milestones and progress")
    async def roadmap_command(interaction: discord.Interaction) -> None:
        """View project milestones and progress."""
        auth_ctx, settings = _context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
            project_id = resolve_project_id(
                auth_ctx.discord_guild_id, auth_ctx.discord_channel_id, "roadmap"
            )
            if project_id is None:
                await _reply(
                    interaction,
                    "**Project Roadmap**\n\nNo project is mapped here. "
                    "Use `/connect-project` first.",
                )
                return
            checker.check_project_access(project_id)
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return

        milestones = repo.list_milestones_for_project(get_conn(), project_id)
        if not milestones:
            await _reply(interaction, "**Project Roadmap**\n\nNo milestones recorded yet.")
            return

        lines = []
        for milestone in milestones:
            target = f" - target {milestone.target_date_utc}" if milestone.target_date_utc else ""
            lines.append(f"- **{milestone.title}** ({milestone.status}){target}")
        await _reply(interaction, "**Project Roadmap**\n\n" + "\n".join(lines))

    @app_commands.command(name="blocker", description="View or record project blockers")
    async def blocker_command(interaction: discord.Interaction) -> None:
        """View or record project blockers."""
        auth_ctx, settings = _context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return
        await _reply(
            interaction,
            "**Project Blockers**\n\nNo blockers recorded. "
            "Use `/note` to record a blocker so it appears in project activity.",
        )

    @app_commands.command(
        name="connect-project", description="Map an approved Discord context to a project"
    )
    async def connect_project_command(interaction: discord.Interaction, project_id: int) -> None:
        """Map an approved Discord context to a project (owner only)."""
        auth_ctx, settings = _context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
            if not auth_ctx.is_owner(settings):
                raise AuthorizationError("Only owners can connect projects.")
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return

        conn = get_conn()
        project = repo.get_project_by_id(conn, project_id)
        if project is None:
            await _reply(interaction, f"Project {project_id} was not found.")
            return
        if not root_is_allowed(project.allowed_root, settings):
            await _reply(
                interaction,
                "Refusing to connect: the project root is outside the configured "
                "PROJECT_ALLOWED_ROOTS.",
            )
            return

        for command_name in MAPPED_COMMANDS:
            repo.upsert_discord_mapping(
                conn,
                project_id=project_id,
                guild_id=auth_ctx.discord_guild_id,
                channel_id=auth_ctx.discord_channel_id,
                command_name=command_name,
            )
        conn.commit()
        await _reply(
            interaction,
            f"Project {project_id} connected to this guild/channel for "
            f"{len(MAPPED_COMMANDS)} commands.",
        )

    @app_commands.command(name="note", description="Save a project note")
    async def note_command(interaction: discord.Interaction, content: str) -> None:
        """Save a project note."""
        auth_ctx, settings = _context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
            project_id = resolve_project_id(
                auth_ctx.discord_guild_id, auth_ctx.discord_channel_id, "note"
            )
            if project_id is None:
                await _reply(
                    interaction,
                    "No project is mapped here. Use `/connect-project` first.",
                )
                return
            checker.check_project_access(project_id)
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return

        if not content.strip():
            await _reply(interaction, "Note content cannot be empty.")
            return

        conn = get_conn()
        note = repo.upsert_note(conn, project_id, auth_ctx.discord_user_id, content.strip())
        conn.commit()
        await _reply(interaction, f"Note saved (#{note.id}): {content.strip()[:100]}")

    @app_commands.command(name="health", description="Inspect project health snapshots")
    async def health_command(interaction: discord.Interaction) -> None:
        """Run a read-only health check and report the stored snapshot."""
        auth_ctx, settings = _context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
            project_id = resolve_project_id(
                auth_ctx.discord_guild_id, auth_ctx.discord_channel_id, "health"
            )
            if project_id is None:
                await _reply(
                    interaction,
                    "**Project Health**\n\nNo project is mapped here. "
                    "Use `/connect-project` first.",
                )
                return
            checker.check_project_access(project_id)
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return

        limited, reset = rate_limiter.check_health_per_hour()
        if limited:
            wait_seconds = max(1, int(reset - monotonic()))
            await _reply(
                interaction,
                f"Health checks are rate limited. Try again in {wait_seconds} seconds.",
            )
            return

        snapshot = check_and_store_health(project_id, settings)
        git_dirty = snapshot.get("git_dirty")
        await _reply(
            interaction,
            f"**Project Health**\n\nStatus: `{snapshot['status']}`\n"
            f"Git dirty: `{git_dirty}`\nChecked: {snapshot['checked_at_utc']}",
        )

else:
    next_command = None  # type: ignore[assignment]
    roadmap_command = None  # type: ignore[assignment]
    blocker_command = None  # type: ignore[assignment]
    connect_project_command = None  # type: ignore[assignment]
    note_command = None  # type: ignore[assignment]
    health_command = None  # type: ignore[assignment]
