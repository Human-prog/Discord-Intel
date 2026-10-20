"""Shared pytest fixtures.

Tests are isolated from the machine environment:
- every settings-related environment variable is removed before each test,
- tests construct Settings with _env_file=None so no developer .env file
  ever influences the run,
- ``app_settings`` points the application at an isolated temporary database,
  temporary project roots, and a temporary session-secret file.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from project_intelligence.config import Settings, env_var_names, load_settings


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture()
def make_settings():
    """Factory that builds Settings with .env loading disabled."""

    def _make(**kwargs) -> Settings:
        kwargs.setdefault("_env_file", None)
        return Settings(**kwargs)

    return _make


@pytest.fixture()
def app_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Settings]:
    """Isolated application environment backed by a temporary database.

    Modules that call ``load_settings()`` (directly or via ``get_conn()``) pick
    these values up from the environment.  The database connection is closed
    before and after the test so no state leaks between tests.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    secret_file = tmp_path / "session_secret"
    secret_file.write_text("s" * 64, encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_PATH", str(data_dir / "test.sqlite3"))
    monkeypatch.setenv("DASHBOARD_SESSION_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("PROJECT_ALLOWED_ROOTS", str(projects_root))
    monkeypatch.setenv("DISCORD_OWNER_USER_IDS", "123456789012345678")

    from project_intelligence.storage import database

    database.close()
    settings = load_settings(env_file=None)
    yield settings
    database.close()


@pytest.fixture()
def db(app_settings: Settings):
    """The migrated SQLite connection for the isolated test database."""
    from project_intelligence.storage.database import get_conn

    return get_conn()
