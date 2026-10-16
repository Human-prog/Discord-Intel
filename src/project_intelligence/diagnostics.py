"""Non-destructive configuration diagnostics (Phase 2).

Builds a summary of effective configuration for humans and future health
endpoints. Secret values are never included: secret settings are reported
as "set" or "unset" only, and runtime checks inspect file existence.

Also provides read-only runtime prerequisite checks (no writes, no service
calls) used by scripts/validate_config.py and, later, by the health engine.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import Settings


def _secret_status(value: Any) -> str:
    return "set" if value is not None else "unset"


def summarize_settings(settings: Settings) -> dict[str, Any]:
    """Return a nested, secret-free summary of the effective configuration."""
    return {
        "app_env": settings.app_env,
        "app_log_level": settings.app_log_level,
        "data_dir": str(settings.data_dir),
        "database_path": str(settings.database_path),
        "discord": {
            "bot_token": _secret_status(settings.discord_bot_token),
            "owner_user_ids": len(settings.discord_owner_user_ids),
            "allowed_guild_ids": len(settings.discord_allowed_guild_ids),
            "allowed_channel_ids": len(settings.discord_allowed_channel_ids),
            "allow_dms": settings.discord_allow_dms,
        },
        "github": {
            "mode": settings.github_mode,
            "allowed_repositories": len(settings.github_allowed_repositories),
            "read_only_token": _secret_status(settings.github_read_only_token),
        },
        "ollama": {
            "base_url": settings.ollama_base_url,
            "model": settings.ollama_model or "unset",
            "timeout_seconds": settings.ollama_timeout_seconds,
        },
        "research": {
            "provider": settings.research_provider or "disabled",
            "api_key": _secret_status(settings.research_api_key),
            "allowed_domains": len(settings.research_allowed_domains),
            "max_results": settings.research_max_results,
            "max_response_bytes": settings.research_max_response_bytes,
        },
        "dashboard": {
            "bind_host": settings.dashboard_bind_host,
            "bind_port": settings.dashboard_bind_port,
            "session_secret_file": (
                str(settings.dashboard_session_secret_file)
                if settings.dashboard_session_secret_file is not None
                else "unset"
            ),
        },
        "projects": {
            "allowed_roots": len(settings.project_allowed_roots),
        },
        "opencode": {
            "enabled": settings.opencode_enabled,
            "command": settings.opencode_command or "unset",
            "allowed_worktrees": len(settings.opencode_allowed_worktrees),
            "max_runtime_seconds": settings.opencode_max_runtime_seconds,
        },
        "scheduler": {
            "enabled": settings.scheduler_enabled,
            "max_concurrent_jobs": settings.max_concurrent_jobs,
            "max_job_runtime_seconds": settings.max_job_runtime_seconds,
        },
        "limits": {
            "max_research_jobs_per_user": settings.max_research_jobs_per_user,
            "audit_retention_days": settings.audit_retention_days,
            "http_timeout_seconds": settings.http_timeout_seconds,
            "http_max_retries": settings.http_max_retries,
        },
    }


def format_summary(summary: dict[str, Any]) -> str:
    """Render a summary dict as human-readable text. Secret-free by construction."""
    discord = summary["discord"]
    github = summary["github"]
    ollama = summary["ollama"]
    research = summary["research"]
    dashboard = summary["dashboard"]
    opencode = summary["opencode"]
    scheduler = summary["scheduler"]
    limits = summary["limits"]

    lines = [
        "Discord Project Intelligence - configuration summary (secrets are never shown)",
        "",
        f"Mode: {summary['app_env']} | Log level: {summary['app_log_level']}",
        f"Data dir: {summary['data_dir']}",
        f"Database: {summary['database_path']}",
        "",
        (
            "Discord: "
            f"token {discord['bot_token']}, owners {discord['owner_user_ids']}, "
            f"guilds {discord['allowed_guild_ids']}, "
            f"channels {discord['allowed_channel_ids']}, "
            f"allow_dms {discord['allow_dms']}"
        ),
        (
            "GitHub: "
            f"mode {github['mode']}, allowed repos {github['allowed_repositories']}, "
            f"token {github['read_only_token']}"
        ),
        (
            "Ollama: "
            f"{ollama['base_url']} (loopback), model {ollama['model']}, "
            f"timeout {ollama['timeout_seconds']}s"
        ),
        (
            "Research: "
            f"provider {research['provider']}, api key {research['api_key']}, "
            f"domains {research['allowed_domains']}, "
            f"max results {research['max_results']}"
        ),
        (
            "Dashboard: "
            f"bind {dashboard['bind_host']}:{dashboard['bind_port']} (loopback), "
            f"session secret file {dashboard['session_secret_file']}"
        ),
        f"Projects: allowed roots {summary['projects']['allowed_roots']}",
        (
            "OpenCode: "
            f"enabled {opencode['enabled']}, command {opencode['command']}, "
            f"worktrees {opencode['allowed_worktrees']}, "
            f"max runtime {opencode['max_runtime_seconds']}s"
        ),
        (
            "Scheduler: "
            f"enabled {scheduler['enabled']}, "
            f"max concurrent jobs {scheduler['max_concurrent_jobs']}, "
            f"max job runtime {scheduler['max_job_runtime_seconds']}s"
        ),
        (
            "Limits: "
            f"research jobs per user {limits['max_research_jobs_per_user']}, "
            f"audit retention {limits['audit_retention_days']}d, "
            f"HTTP timeout {limits['http_timeout_seconds']}s, "
            f"HTTP retries {limits['http_max_retries']}"
        ),
    ]
    return "\n".join(lines)


def check_runtime_prerequisites(settings: Settings) -> list[tuple[str, str]]:
    """Read-only checks of paths/commands referenced by the configuration.

    Returns a list of (level, message) where level is "info" or "error".
    Performs no writes and no network access.
    """
    checks: list[tuple[str, str]] = []

    if not Path(settings.data_dir).exists():
        checks.append(
            (
                "info",
                f"data directory does not exist yet: {settings.data_dir} "
                "(it will be created at service startup in later phases)",
            )
        )

    if settings.github_mode == "app":
        key_file = settings.github_app_private_key_file
        if key_file is None or not Path(key_file).exists():
            checks.append(
                ("error", f"GitHub App private key file not found: {key_file}")
            )

    if (
        settings.dashboard_session_secret_file is not None
        and not Path(settings.dashboard_session_secret_file).exists()
    ):
        checks.append(
            (
                "error",
                "dashboard session secret file not found: "
                f"{settings.dashboard_session_secret_file}",
            )
        )

    if settings.opencode_enabled and settings.opencode_command:
        if shutil.which(settings.opencode_command) is None:
            checks.append(
                (
                    "error",
                    f"OpenCode command not found on PATH: {settings.opencode_command}",
                )
            )

    return checks
