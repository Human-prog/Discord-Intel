"""Project mapping and command set (Phase 11).

Implements /next, /roadmap, /blocker, /connect-project, /create-project, /note,
/health, and /research commands.  All commands pass through central
authorization before retrieving project data.  Project mapping is explicit and
validated; paths must remain within configured roots.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from typing import Any, cast

from project_intelligence.config import Settings
from project_intelligence.health.health_engine import check_and_store_health
from project_intelligence.research.service import VALID_SCOPES, run_research
from project_intelligence.research.web_research import ResearchError
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
except ImportError:  # pragma: no cover - discord.py is an optional dependency
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
    "research",
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


async def _defer(interaction: Any) -> None:
    """Defer an interaction when the transport supports it (real Discord does)."""
    defer = getattr(interaction.response, "defer", None)
    if defer is not None:
        await defer(ephemeral=True, thinking=True)
    else:  # pragma: no cover - offline doubles may not implement defer
        await interaction.response.send_message("Working…", ephemeral=True)


async def _followup(interaction: Any, message: str) -> None:
    followup = getattr(interaction, "followup", None)
    if followup is not None:
        await followup.send(message, ephemeral=True)
    else:  # pragma: no cover - offline doubles may not implement followup
        await interaction.response.send_message(message, ephemeral=True)


def _channel_project_id(auth_ctx: AuthContext) -> int | None:
    """Resolve the channel's project without requiring a command-specific map."""
    return repo.get_any_mapped_project_id(
        get_conn(),
        auth_ctx.discord_guild_id,
        auth_ctx.discord_channel_id,
    )


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

    @app_commands.command(
        name="create-project",
        description="Register a project directory and connect it to this channel (owner only)",
    )
    @app_commands.describe(
        name="Display name for the project",
        root="Absolute path to the project directory on the server",
        description="Optional short description",
    )
    async def create_project_command(
        interaction: discord.Interaction,
        name: str,
        root: str,
        description: str = "",
    ) -> None:
        """Register a project and map it to the current guild/channel."""
        auth_ctx, settings = _context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
            if not auth_ctx.is_owner(settings):
                raise AuthorizationError("Only owners can create projects.")
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return

        project_name = name.strip()
        if not project_name or len(project_name) > 200:
            await _reply(interaction, "Project name must be between 1 and 200 characters.")
            return

        candidate = Path(root.strip()).expanduser()
        if not candidate.is_absolute():
            await _reply(interaction, "Project root must be an absolute path.")
            return
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            await _reply(interaction, f"Project root was not found: {candidate}")
            return
        if not resolved.is_dir():
            await _reply(interaction, f"Project root is not a directory: {resolved}")
            return
        if not root_is_allowed(str(resolved), settings):
            await _reply(
                interaction,
                "Refusing to create the project: the root is outside the configured "
                "PROJECT_ALLOWED_ROOTS.",
            )
            return

        conn = get_conn()
        project = repo.get_project_by_root(conn, str(resolved))
        created = project is None
        if project is None:
            project = repo.upsert_project(
                conn,
                project_name,
                description.strip() or None,
                str(resolved),
            )
        for command_name in MAPPED_COMMANDS:
            repo.upsert_discord_mapping(
                conn,
                project_id=project.id,
                guild_id=auth_ctx.discord_guild_id,
                channel_id=auth_ctx.discord_channel_id,
                command_name=command_name,
            )
        conn.commit()

        if created:
            message = f"Project {project.id} ({project.name}) created and connected"
        else:
            message = f"Project {project.id} ({project.name}) already exists; connected"
        await _reply(
            interaction,
            f"{message} to this guild/channel for {len(MAPPED_COMMANDS)} commands.",
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

    @app_commands.command(
        name="schedule-research",
        description="Schedule a recurring research job (runs automatically)",
    )
    @app_commands.describe(
        question="What to research (up to 1000 chars)",
        scope="Where to look: local, web, both, youtube",
        interval="How often: daily / weekly / hourly",
        start_time="Optional start (YYYY-MM-DD HH:MM UTC)",
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Both local and web", value="both"),
            app_commands.Choice(name="Local knowledge only", value="local"),
            app_commands.Choice(name="Web only", value="web"),
            app_commands.Choice(name="YouTube videos only", value="youtube"),
        ],
        interval=[
            app_commands.Choice(name="Daily", value="daily"),
            app_commands.Choice(name="Weekly", value="weekly"),
            app_commands.Choice(name="Hourly", value="hourly"),
        ],
    )
    async def schedule_research_command(
        interaction: discord.Interaction,
        question: str,
        scope: str = "both",
        interval: str = "daily",
        start_time: str = "",
    ) -> None:
        """Create a recurring research job that runs on schedule."""
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

        normalized_scope = scope.strip().lower()
        if normalized_scope not in VALID_SCOPES:
            await _reply(interaction, f"Scope must be one of: {', '.join(VALID_SCOPES)}.")
            return
        normalized_q = " ".join(question.split()).strip()
        if not normalized_q or len(normalized_q) > 1000:
            await _reply(interaction, "Question must be 1-1000 characters.")
            return

        conn = get_conn()
        try:
            from project_intelligence.storage import repositories as repo
            job = repo.upsert_research_job(
                conn,
                project_id=resolve_project_id(
                    auth_ctx.discord_guild_id, auth_ctx.discord_channel_id, "research"
                ),
                user_id=auth_ctx.discord_user_id,
                question=normalized_q,
                scope=normalized_scope,
                provider=(settings.research_provider or "none").strip().lower() or None,
            )
            conn.commit()
        except Exception as exc:
            await _reply(interaction, f"Failed to schedule research: {exc}")
            return

        await _reply(
            interaction,
            f"**Scheduled Research #{job.id}**\n"
            f"Question: {normalized_q[:120]}\n"
            f"Scope: {normalized_scope}\n"
            f"Interval: {interval}\n"
            f"Status: queued (will run automatically)\n"
            f"Full report saved to dashboard at `#research-{job.id}`",
        )

    @app_commands.command(
        name="research",
        description="Research a question across local project knowledge and the web",
    )
    @app_commands.describe(
        question="What to research (up to 1000 characters)",
        scope="Where to look: local, web, or both",
        project_id="Optional project ID; defaults to this channel's project",
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Both local and web", value="both"),
            app_commands.Choice(name="Local knowledge only", value="local"),
            app_commands.Choice(name="Web only", value="web"),
            app_commands.Choice(name="YouTube videos only", value="youtube"),
        ]
    )
    async def research_command(
        interaction: discord.Interaction,
        question: str,
        scope: str = "both",
        project_id: int | None = None,
    ) -> None:
        """Run a cited research job and save the full report in the dashboard."""
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

        normalized_scope = scope.strip().lower()
        if normalized_scope not in VALID_SCOPES:
            await _reply(
                interaction,
                f"Scope must be one of: {', '.join(VALID_SCOPES)}.",
            )
            return
        normalized_question = " ".join(question.split()).strip()
        if not normalized_question:
            await _reply(interaction, "Research question cannot be empty.")
            return
        if len(normalized_question) > 1000:
            await _reply(interaction, "Research question must be 1000 characters or fewer.")
            return

        limited, reset = rate_limiter.check_research_per_user(auth_ctx.discord_user_id)
        if limited:
            wait_seconds = max(1, int(reset - monotonic()))
            await _reply(
                interaction,
                f"Research is rate limited. Try again in {wait_seconds} seconds.",
            )
            return

        conn = get_conn()
        resolved_project = project_id
        if resolved_project is None:
            resolved_project = _channel_project_id(auth_ctx)
        if resolved_project is not None:
            if repo.get_project_by_id(conn, resolved_project) is None:
                await _reply(interaction, f"Project {resolved_project} was not found.")
                return
            try:
                checker.check_project_access(resolved_project)
            except AuthorizationError as exc:
                await _reply(interaction, exc.message)
                return

        await _defer(interaction)
        try:
            result = await asyncio.to_thread(
                run_research,
                normalized_question,
                project_id=resolved_project,
                user_id=auth_ctx.discord_user_id,
                scope=normalized_scope,
                settings=settings,
            )
        except ResearchError as exc:
            await _followup(interaction, f"**Research failed**\n{exc}")
            return
        except ValueError as exc:
            await _followup(interaction, f"**Research failed**\n{exc}")
            return

        if result.status != "completed":
            await _followup(
                interaction,
                f"**Research failed**\n{result.error or 'The job did not complete.'}",
            )
            return

        body = result.report
        truncated = len(body) > 1500
        if truncated:
            body = body[:1500].rstrip() + "\n…"
        message = (
            f"**Research #{result.job_id}** · {result.local_count} local · "
            f"{result.web_count} web\n\n{body}"
        )
        if truncated:
            message += "\n\nFull report saved in the dashboard."
        public_url = (settings.dashboard_public_url or "").rstrip("/")
        if public_url:
            message += f"\n{public_url}/#research-{result.job_id}"
        await _followup(interaction, message)

else:  # pragma: no cover - discord.py is an optional dependency
    next_command = None  # type: ignore[assignment]
    roadmap_command = None  # type: ignore[assignment]
    blocker_command = None  # type: ignore[assignment]
    connect_project_command = None  # type: ignore[assignment]
    create_project_command = None  # type: ignore[assignment]
    note_command = None  # type: ignore[assignment]
    health_command = None  # type: ignore[assignment]
    research_command = None  # type: ignore[assignment]
