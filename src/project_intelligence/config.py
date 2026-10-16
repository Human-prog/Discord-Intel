"""Typed application configuration with fail-closed validation (Phase 2).

Rules enforced here:
- External integrations are disabled unless explicitly configured.
- The dashboard binds to loopback only (remote access comes later via
  Tailscale Serve, never via a non-loopback bind).
- Ollama must be reached over a loopback address.
- Missing allowlists deny everything by default.
- A Discord bot token without explicit owner user IDs is refused.
- Production mode rejects placeholder-looking secrets, relative data paths,
  and a missing session-secret file reference.
- Validation error messages never contain secret values.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ENVS = ("development", "testing", "production")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
GITHUB_MODES = ("disabled", "app", "token")

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_DOMAIN_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$")

# Only enforced in production; the offending value is never echoed.
_PLACEHOLDER_MARKERS = (
    "changeme",
    "change-me",
    "placeholder",
    "example",
    "dummy",
    "your-",
    "your_",
    "<",
    ">",
    "xxx",
    "todo",
)

# Fields that treat an empty string in the environment as "unset".
_BLANK_TO_NONE_FIELDS = (
    "database_path",
    "discord_bot_token",
    "github_app_id",
    "github_installation_id",
    "github_app_private_key_file",
    "github_read_only_token",
    "ollama_model",
    "research_provider",
    "research_api_key",
    "dashboard_session_secret_file",
    "opencode_command",
)

_SECRET_FIELDS = ("discord_bot_token", "github_read_only_token", "research_api_key")


def is_loopback_host(host: str) -> bool:
    """True for loopback hostnames/addresses (127.0.0.0/8, ::1, localhost)."""
    if host.lower() in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.replace("\n", ",").split(",") if part.strip()]


class ConfigError(Exception):
    """Raised when configuration is invalid. The message never contains secrets."""


class Settings(BaseSettings):
    """Application settings, loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Never JSON-decode complex env values; our validators parse raw strings.
        enable_decoding=False,
    )

    # --- application ---
    app_env: str = "development"
    app_log_level: str = "INFO"
    data_dir: Path = Path("data")
    database_path: Path | None = None

    # --- discord ---
    discord_bot_token: SecretStr | None = None
    discord_owner_user_ids: list[int] = Field(default_factory=list)
    discord_allowed_guild_ids: list[int] = Field(default_factory=list)
    discord_allowed_channel_ids: list[int] = Field(default_factory=list)
    discord_allow_dms: bool = False

    # --- github (read-only) ---
    github_mode: str = "disabled"
    github_app_id: int | None = None
    github_app_private_key_file: Path | None = None
    github_installation_id: int | None = None
    github_allowed_repositories: list[str] = Field(default_factory=list)
    github_read_only_token: SecretStr | None = None

    # --- ollama (loopback only) ---
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str | None = None
    ollama_timeout_seconds: int = Field(default=120, ge=1, le=600)

    # --- research ---
    research_provider: str | None = None
    research_api_key: SecretStr | None = None
    research_allowed_domains: list[str] = Field(default_factory=list)
    research_max_results: int = Field(default=10, ge=1, le=50)
    research_max_response_bytes: int = Field(default=5_000_000, ge=10_000, le=50_000_000)

    # --- dashboard (loopback only) ---
    dashboard_bind_host: str = "127.0.0.1"
    dashboard_bind_port: int = Field(default=8765, ge=1, le=65535)
    dashboard_session_secret_file: Path | None = None

    # --- projects ---
    project_allowed_roots: list[Path] = Field(default_factory=list)

    # --- jobs & limits ---
    scheduler_enabled: bool = False
    max_concurrent_jobs: int = Field(default=2, ge=1, le=10)
    max_research_jobs_per_user: int = Field(default=3, ge=1, le=20)
    max_job_runtime_seconds: int = Field(default=600, ge=30, le=3600)
    audit_retention_days: int = Field(default=90, ge=7, le=3650)

    # --- network behavior ---
    http_timeout_seconds: int = Field(default=15, ge=1, le=120)
    http_max_retries: int = Field(default=2, ge=0, le=5)

    # --- opencode (disabled by default) ---
    opencode_enabled: bool = False
    opencode_command: str | None = None
    opencode_allowed_worktrees: list[Path] = Field(default_factory=list)
    opencode_max_runtime_seconds: int = Field(default=300, ge=30, le=1800)

    # ------------------------------------------------------------------ #
    # field validators
    # ------------------------------------------------------------------ #

    @field_validator("app_env", mode="before")
    @classmethod
    def _check_app_env(cls, v: Any) -> str:
        value = str(v).strip().lower()
        if value not in APP_ENVS:
            raise ValueError(f"APP_ENV must be one of: {', '.join(APP_ENVS)}")
        return value

    @field_validator("app_log_level", mode="before")
    @classmethod
    def _check_log_level(cls, v: Any) -> str:
        value = str(v).strip().upper()
        if value not in LOG_LEVELS:
            raise ValueError(f"APP_LOG_LEVEL must be one of: {', '.join(LOG_LEVELS)}")
        return value

    @field_validator("github_mode", mode="before")
    @classmethod
    def _check_github_mode(cls, v: Any) -> str:
        value = str(v).strip().lower()
        if value not in GITHUB_MODES:
            raise ValueError(f"GITHUB_MODE must be one of: {', '.join(GITHUB_MODES)}")
        return value

    @field_validator("data_dir", mode="before")
    @classmethod
    def _data_dir_not_blank(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            raise ValueError("DATA_DIR must not be empty")
        return v

    @field_validator(*_BLANK_TO_NONE_FIELDS, mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator(
        "discord_owner_user_ids",
        "discord_allowed_guild_ids",
        "discord_allowed_channel_ids",
        mode="before",
    )
    @classmethod
    def _parse_id_list(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if isinstance(v, str):
            raw = v.replace("\n", ",").replace(" ", ",")
            parts = [p for p in raw.split(",") if p.strip()]
            v = parts
        if isinstance(v, (list, tuple)):
            result: list[int] = []
            seen: set[int] = set()
            for item in v:
                try:
                    number = int(item)
                except (TypeError, ValueError):
                    raise ValueError(
                        "must be a comma-separated list of numeric Discord IDs"
                    ) from None
                if number < 1:
                    raise ValueError("Discord IDs must be positive numbers")
                if number not in seen:
                    seen.add(number)
                    result.append(number)
            return result
        raise ValueError("must be a comma-separated list of numeric Discord IDs")

    @field_validator("github_allowed_repositories", mode="before")
    @classmethod
    def _parse_repositories(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            v = _split_csv(v.replace("\n", ","))
        if not isinstance(v, (list, tuple)):
            raise ValueError("must be a comma-separated list of owner/repo names")
        result: list[str] = []
        for item in v:
            name = str(item).strip()
            if not _REPO_NAME_RE.match(name):
                raise ValueError(
                    "each repository must look like 'owner/repo' (no URLs, no extra path segments)"
                )
            result.append(name)
        return result

    @field_validator("research_allowed_domains", mode="before")
    @classmethod
    def _parse_domains(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            v = _split_csv(v.replace("\n", ","))
        if not isinstance(v, (list, tuple)):
            raise ValueError("must be a comma-separated list of bare domains")
        result: list[str] = []
        for item in v:
            domain = str(item).strip().lower()
            if not _DOMAIN_RE.match(domain):
                raise ValueError(
                    "each allowed domain must be a bare domain name "
                    "(for example: docs.python.org), without scheme or path"
                )
            result.append(domain)
        return result

    @field_validator("project_allowed_roots", "opencode_allowed_worktrees", mode="before")
    @classmethod
    def _parse_path_list(cls, v: Any) -> list[Path]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            raw = v.replace(";", ",").replace("\n", ",")
            v = [part.strip() for part in raw.split(",") if part.strip()]
        if not isinstance(v, (list, tuple)):
            raise ValueError("must be a comma-separated list of paths")
        return [Path(str(item)) for item in v if str(item).strip()]

    @field_validator("ollama_base_url")
    @classmethod
    def _ollama_must_be_loopback(cls, v: str) -> str:
        parts = urlsplit(v.strip())
        if parts.scheme not in ("http", "https"):
            raise ValueError("OLLAMA_BASE_URL must use http or https")
        host = parts.hostname
        if host is None or not is_loopback_host(host):
            raise ValueError(
                "OLLAMA_BASE_URL must point to a loopback address "
                "(127.0.0.1, ::1, or localhost); a remote Ollama requires a "
                "separately approved, authenticated design"
            )
        return v.strip().rstrip("/")

    @field_validator("dashboard_bind_host")
    @classmethod
    def _dashboard_must_be_loopback(cls, v: str) -> str:
        host = v.strip()
        if not is_loopback_host(host):
            raise ValueError(
                "DASHBOARD_BIND_HOST must be a loopback address "
                "(127.0.0.1, ::1, or localhost); remote access is only via "
                "Tailscale Serve with application authentication"
            )
        return host

    # ------------------------------------------------------------------ #
    # cross-field validation
    # ------------------------------------------------------------------ #

    @model_validator(mode="after")
    def _finalize_and_check(self) -> Settings:
        # Derive the database path when unset.
        if self.database_path is None:
            self.database_path = Path(self.data_dir) / "db.sqlite3"

        # Discord: a token without an explicit owner is unsafe (fail closed).
        if self.discord_bot_token is not None and not self.discord_owner_user_ids:
            raise ValueError(
                "DISCORD_BOT_TOKEN is set but DISCORD_OWNER_USER_IDS is empty; "
                "refusing to run Discord without an explicit owner"
            )

        # GitHub: the selected mode must have the credentials it needs.
        if self.github_mode == "token" and self.github_read_only_token is None:
            raise ValueError("GITHUB_MODE=token requires GITHUB_READ_ONLY_TOKEN")
        if self.github_mode == "app":
            if self.github_app_id is None:
                raise ValueError("GITHUB_MODE=app requires GITHUB_APP_ID")
            if self.github_app_private_key_file is None:
                raise ValueError("GITHUB_MODE=app requires GITHUB_APP_PRIVATE_KEY_FILE")

        # OpenCode: enabling it requires an explicit command and scoped worktrees.
        if self.opencode_enabled:
            if not self.opencode_command:
                raise ValueError(
                    "OPENCODE_ENABLED=true requires OPENCODE_COMMAND; "
                    "the integration is disabled by default by design"
                )
            if not self.opencode_allowed_worktrees:
                raise ValueError(
                    "OPENCODE_ENABLED=true requires OPENCODE_ALLOWED_WORKTREES; "
                    "the integration is scoped to explicit worktrees"
                )

        # Production hardening: no ambiguous paths, no missing secrets, no placeholders.
        if self.app_env == "production":
            if not Path(self.data_dir).is_absolute():
                raise ValueError(
                    "production requires an absolute DATA_DIR "
                    "(relative paths depend on the working directory)"
                )
            if not Path(self.database_path).is_absolute():
                raise ValueError(
                    "production requires an absolute DATABASE_PATH "
                    "(or an absolute DATA_DIR to derive it from)"
                )
            if self.dashboard_session_secret_file is None:
                raise ValueError(
                    "production requires DASHBOARD_SESSION_SECRET_FILE "
                    "(no implicit session secret is ever generated)"
                )
            for field_name in _SECRET_FIELDS:
                secret = getattr(self, field_name)
                if secret is None:
                    continue
                lowered = secret.get_secret_value().strip().lower()
                if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
                    raise ValueError(
                        f"{field_name.upper()} looks like a placeholder value; "
                        "production requires a real secret or the field unset"
                    )
        return self


def env_var_names() -> tuple[str, ...]:
    """Environment variable names derived from the settings fields."""
    return tuple("".join(name.upper()) for name in Settings.model_fields)


def load_settings(*, env_file: str | Path | None = ".env") -> Settings:
    """Load and validate settings.

    Raises ConfigError with a secret-free message when configuration is invalid.
    Pass env_file=None to ignore any .env file (used by tests).
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from None


def _format_validation_error(exc: ValidationError) -> str:
    lines = ["configuration is invalid:"]
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", ())) or "(model)"
        lines.append(f"  - {location}: {err.get('msg', 'invalid value')}")
    return "\n".join(lines)
