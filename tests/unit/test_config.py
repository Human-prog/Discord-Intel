"""Unit tests for src/project_intelligence/config.py.

Covers: secure defaults, env parsing, invalid/missing/conflicting settings,
loopback enforcement, production hardening, placeholder rejection, and the
committed .env.example being a valid development configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values
from pydantic import ValidationError

from project_intelligence.config import (
    ConfigError,
    Settings,
    env_var_names,
    load_settings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------- #
# defaults
# --------------------------------------------------------------------- #


def test_defaults_are_secure(make_settings):
    s = make_settings()
    assert s.app_env == "development"
    assert s.app_log_level == "INFO"
    assert s.database_path == Path("data") / "db.sqlite3"
    assert s.discord_bot_token is None
    assert s.discord_allow_dms is False
    assert s.discord_owner_user_ids == []
    assert s.github_mode == "disabled"
    assert s.github_allowed_repositories == []
    assert s.ollama_base_url == "http://127.0.0.1:11434"
    assert s.dashboard_bind_host == "127.0.0.1"
    assert s.dashboard_bind_port == 8765
    assert s.opencode_enabled is False
    assert s.scheduler_enabled is False
    assert s.project_allowed_roots == []
    assert s.research_provider is None


def test_env_var_names_helper():
    names = env_var_names()
    assert "APP_ENV" in names
    assert "DISCORD_BOT_TOKEN" in names
    assert "OPENCODE_ENABLED" in names


# --------------------------------------------------------------------- #
# environment parsing
# --------------------------------------------------------------------- #


def test_owner_ids_parsed_from_comma_separated_env(make_settings, monkeypatch):
    monkeypatch.setenv("DISCORD_OWNER_USER_IDS", "111, 222 ,333")
    s = make_settings()
    assert s.discord_owner_user_ids == [111, 222, 333]


def test_ids_reject_non_numeric_values(make_settings, monkeypatch):
    monkeypatch.setenv("DISCORD_OWNER_USER_IDS", "abc")
    with pytest.raises(ValidationError):
        make_settings()


def test_ids_deduplicate(make_settings):
    s = make_settings(discord_owner_user_ids=[5, 5, 7])
    assert s.discord_owner_user_ids == [5, 7]


def test_paths_parsed_from_semicolon_and_comma(make_settings):
    s = make_settings(project_allowed_roots="C:/a;C:/b,C:/c")
    assert s.project_allowed_roots == [Path("C:/a"), Path("C:/b"), Path("C:/c")]


# --------------------------------------------------------------------- #
# discord fail-closed rules
# --------------------------------------------------------------------- #


def test_discord_token_requires_owner(make_settings):
    with pytest.raises(ValidationError) as excinfo:
        make_settings(discord_bot_token="123456:ABCdef-ghijklmnopqrstuvwxyz")
    assert "DISCORD_OWNER_USER_IDS" in excinfo.value.errors()[0]["msg"]


def test_discord_token_with_owner_is_accepted(make_settings):
    s = make_settings(
        discord_bot_token="123456:ABCdef-ghijklmnopqrstuvwxyz",
        discord_owner_user_ids=[1],
    )
    assert s.discord_bot_token is not None


# --------------------------------------------------------------------- #
# github mode consistency
# --------------------------------------------------------------------- #


def test_github_token_mode_requires_token(make_settings):
    with pytest.raises(ValidationError):
        make_settings(github_mode="token")


def test_github_token_mode_with_token_ok(make_settings):
    s = make_settings(github_mode="token", github_read_only_token="ghp_" + "a" * 30)
    assert s.github_mode == "token"


def test_github_app_mode_requires_app_id_and_key_file(make_settings, tmp_path):
    with pytest.raises(ValidationError):
        make_settings(github_mode="app")
    with pytest.raises(ValidationError):
        make_settings(github_mode="app", github_app_id=42)
    s = make_settings(
        github_mode="app",
        github_app_id=42,
        github_app_private_key_file=str(tmp_path / "key.pem"),
    )
    assert s.github_mode == "app"


@pytest.mark.parametrize(
    "bad_value",
    ["https://github.com/a/b", "a/b/c", "not-a-repo", "a b"],
)
def test_github_repos_reject_invalid_formats(make_settings, bad_value):
    with pytest.raises(ValidationError):
        make_settings(github_allowed_repositories=[bad_value])


def test_github_repos_accept_valid_formats(make_settings):
    s = make_settings(
        github_allowed_repositories="Human-prog/Discord-Intel,owner2/repo.name"
    )
    assert s.github_allowed_repositories == ["Human-prog/Discord-Intel", "owner2/repo.name"]


def test_github_mode_enum_rejects_unknown(make_settings):
    with pytest.raises(ValidationError):
        make_settings(github_mode="readwrite")


# --------------------------------------------------------------------- #
# loopback enforcement
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://192.168.1.50:11434",
        "http://example.com:11434",
        "https://10.0.0.5:11434",
    ],
)
def test_ollama_rejects_non_loopback_hosts(make_settings, bad_url):
    with pytest.raises(ValidationError):
        make_settings(ollama_base_url=bad_url)


@pytest.mark.parametrize("bad_url", ["file:///etc/passwd", "ftp://127.0.0.1"])
def test_ollama_rejects_bad_schemes(make_settings, bad_url):
    with pytest.raises(ValidationError):
        make_settings(ollama_base_url=bad_url)


@pytest.mark.parametrize(
    ("good_url", "normalized"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
        ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
    ],
)
def test_ollama_accepts_loopback_variants(make_settings, good_url, normalized):
    s = make_settings(ollama_base_url=good_url)
    assert s.ollama_base_url == normalized


@pytest.mark.parametrize("bad_host", ["0.0.0.0", "192.168.1.19", "::"])
def test_dashboard_rejects_non_loopback_hosts(make_settings, bad_host):
    with pytest.raises(ValidationError):
        make_settings(dashboard_bind_host=bad_host)


@pytest.mark.parametrize("bad_host", ["0.0.0.0", "192.168.1.19"])
def test_dashboard_rejects_non_loopback_in_production(make_settings, bad_host, tmp_path):
    with pytest.raises(ValidationError):
        make_settings(
            app_env="production",
            data_dir=str(tmp_path),
            dashboard_session_secret_file=str(tmp_path / "secret"),
            dashboard_bind_host=bad_host,
        )


@pytest.mark.parametrize("bad_port", [0, 65536])
def test_dashboard_port_bounds(make_settings, bad_port):
    with pytest.raises(ValidationError):
        make_settings(dashboard_bind_port=bad_port)


# --------------------------------------------------------------------- #
# enums and bounds
# --------------------------------------------------------------------- #


def test_log_level_enum_and_normalization(make_settings):
    with pytest.raises(ValidationError):
        make_settings(app_log_level="VERBOSE")
    assert make_settings(app_log_level="debug").app_log_level == "DEBUG"


def test_app_env_enum_and_normalization(make_settings):
    with pytest.raises(ValidationError):
        make_settings(app_env="prod")
    assert make_settings(app_env="Development").app_env == "development"


@pytest.mark.parametrize("bad_value", [0, 51])
def test_research_max_results_bounds(make_settings, bad_value):
    with pytest.raises(ValidationError):
        make_settings(research_max_results=bad_value)


def test_job_limit_bounds(make_settings):
    with pytest.raises(ValidationError):
        make_settings(max_concurrent_jobs=0)
    with pytest.raises(ValidationError):
        make_settings(max_job_runtime_seconds=10)


def test_research_domains_reject_urls(make_settings):
    with pytest.raises(ValidationError):
        make_settings(research_allowed_domains=["https://docs.python.org/3/"])
    s = make_settings(research_allowed_domains="docs.python.org, ollama.com")
    assert s.research_allowed_domains == ["docs.python.org", "ollama.com"]


# --------------------------------------------------------------------- #
# empty values and opencode
# --------------------------------------------------------------------- #


def test_empty_strings_treated_as_unset(make_settings):
    s = make_settings(
        github_read_only_token="",
        research_provider="",
        database_path="",
        dashboard_session_secret_file="",
    )
    assert s.github_read_only_token is None
    assert s.research_provider is None
    assert s.dashboard_session_secret_file is None
    assert s.database_path == Path("data") / "db.sqlite3"


def test_opencode_disabled_by_default_and_requires_config(make_settings, tmp_path):
    assert make_settings().opencode_enabled is False
    with pytest.raises(ValidationError):
        make_settings(opencode_enabled=True)
    with pytest.raises(ValidationError):
        make_settings(opencode_enabled=True, opencode_command="opencode")
    s = make_settings(
        opencode_enabled=True,
        opencode_command="opencode",
        opencode_allowed_worktrees=[str(tmp_path)],
    )
    assert s.opencode_enabled is True


# --------------------------------------------------------------------- #
# production hardening
# --------------------------------------------------------------------- #


def test_production_rejects_relative_data_dir(make_settings, tmp_path):
    with pytest.raises(ValidationError):
        make_settings(
            app_env="production",
            data_dir="data",
            dashboard_session_secret_file=str(tmp_path / "secret"),
        )


def test_production_requires_session_secret_file(make_settings, tmp_path):
    with pytest.raises(ValidationError) as excinfo:
        make_settings(app_env="production", data_dir=str(tmp_path))
    assert "DASHBOARD_SESSION_SECRET_FILE" in excinfo.value.errors()[0]["msg"]


def test_production_rejects_placeholder_secrets(make_settings, tmp_path):
    with pytest.raises(ValidationError) as excinfo:
        make_settings(
            app_env="production",
            data_dir=str(tmp_path),
            dashboard_session_secret_file=str(tmp_path / "secret"),
            discord_bot_token="changeme",
            discord_owner_user_ids=[1],
        )
    message = excinfo.value.errors()[0]["msg"]
    assert "placeholder" in message
    # The offending value must not appear anywhere in the error rendering.
    assert "changeme" not in str(excinfo.value)


def test_production_accepts_absolute_paths_and_real_secret(make_settings, tmp_path):
    s = make_settings(
        app_env="production",
        data_dir=str(tmp_path),
        dashboard_session_secret_file=str(tmp_path / "secret"),
        github_mode="token",
        github_read_only_token="Aa1Bb2Cc3Dd4Ee5Ff6Gg7Hh8Ii9Jj0Kk1Ll2Mm3Nn4Oo5Pp6",
    )
    assert s.app_env == "production"
    assert Path(s.database_path).is_absolute()


# --------------------------------------------------------------------- #
# load_settings and the committed example file
# --------------------------------------------------------------------- #


def test_load_settings_wraps_validation_errors(monkeypatch):
    monkeypatch.setenv("APP_ENV", "not-a-mode")
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=None)
    assert "APP_ENV" in str(excinfo.value)
    assert "not-a-mode" not in str(excinfo.value)


def test_env_example_file_is_valid_dev_config(make_settings):
    example_path = REPO_ROOT / ".env.example"
    assert example_path.exists(), "committed .env.example must exist"
    values = dotenv_values(example_path)
    kwargs = {key.lower(): value for key, value in values.items()}
    s = make_settings(**kwargs)
    assert s.app_env == "development"
    assert s.github_mode == "disabled"
    assert s.opencode_enabled is False
    assert s.scheduler_enabled is False
