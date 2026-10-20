"""Focused coverage of defensive branches and factory defaults."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from project_intelligence.discord import bot as bot_module
from project_intelligence.discord.commands import project_commands as commands
from project_intelligence.health import health_engine
from project_intelligence.health.health_engine import _check_path_exists, check_project_health
from project_intelligence.integrations import ollama as ollama_module
from project_intelligence.integrations.github import GitHubIntegration
from project_intelligence.integrations.ollama import (
    ModelAdapter,
    OllamaClient,
    create_model_adapter,
    create_ollama_client,
)
from project_intelligence.integrations.opencode import create_mock_adapter
from project_intelligence.jobs import scheduler as scheduler_module
from project_intelligence.jobs.scheduler import Scheduler, create_scheduler
from project_intelligence.research import research_pipeline
from project_intelligence.research.research_pipeline import (
    ResearchPipeline,
    create_research_pipeline,
)
from project_intelligence.security.authentication import AuthContext
from project_intelligence.security.authorization import AuthorizationError, make_checker
from project_intelligence.storage import database
from project_intelligence.storage import repositories as repo

from ..discord.helpers import CHANNEL_ID, GUILD_ID, OTHER_USER_ID, OWNER_ID, FakeInteraction


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Repository defensive paths
# ---------------------------------------------------------------------------


class _NullCursor:
    def fetchone(self):
        return None


class _NullConn:
    def execute(self, *args, **kwargs):
        return _NullCursor()


@pytest.mark.parametrize(
    "call",
    [
        lambda c: repo.upsert_project(c, "P", None, "/srv/p"),
        lambda c: repo.upsert_project_source(c, 1, "github", "owner/repo", None),
        lambda c: repo.upsert_discord_mapping(c, 1, 2, 3, "next"),
        lambda c: repo.upsert_authorized_user(c, 1, 1),
        lambda c: repo.upsert_note(c, 1, 1, "content"),
        lambda c: repo.upsert_milestone(c, 1, "Title", None, "open", None),
        lambda c: repo.upsert_evidence(c, 1, None, "Title", "hash", 1.0, None),
        lambda c: repo.upsert_repository_snapshot(c, 1, "head", "main", None),
        lambda c: repo.upsert_research_job(c, 1, None, "question"),
        lambda c: repo.upsert_research_source(c, 1, "Title", None, "web", "hash"),
    ],
)
def test_upserts_fail_loudly_when_sqlite_returns_no_row(call) -> None:
    with pytest.raises(ValueError, match="returned no row"):
        call(_NullConn())


# ---------------------------------------------------------------------------
# Authorization edge paths
# ---------------------------------------------------------------------------


def test_direct_messages_are_rejected(app_settings) -> None:
    ctx = AuthContext(
        discord_user_id=OWNER_ID,
        discord_guild_id=None,  # type: ignore[arg-type] - DM simulation
        discord_channel_id=CHANNEL_ID,
    )
    with pytest.raises(AuthorizationError, match="DM"):
        make_checker(ctx, app_settings).check_user_is_member_of_guild()


def test_owner_or_project_rejects_unrelated_user(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    ctx = AuthContext(
        discord_user_id=OTHER_USER_ID,
        discord_guild_id=GUILD_ID,
        discord_channel_id=CHANNEL_ID,
    )
    with pytest.raises(AuthorizationError, match="not authorized"):
        make_checker(ctx, app_settings).check_owner_or_project(project.id)


# ---------------------------------------------------------------------------
# Health engine: Git HEAD variants and path errors
# ---------------------------------------------------------------------------


def test_path_check_handles_resolution_errors(tmp_path: Path, monkeypatch) -> None:
    def _raise(self):
        raise OSError("permission denied")

    monkeypatch.setattr(health_engine.Path, "resolve", _raise)
    result = _check_path_exists(tmp_path, Path("."))
    assert result["status"] == "failed"
    assert "permission denied" in result["reason"]


def _project_with_fake_git(db, root: Path):
    (root / ".git").mkdir(parents=True)
    return repo.upsert_project(db, "Alpha", None, str(root))


def test_git_head_with_missing_ref_file_is_still_reported(db, app_settings, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    project = _project_with_fake_git(db, root)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    result = check_project_health(project.id, app_settings)
    assert result["git_head"] == "ref: refs/heads/main"


def test_detached_git_head_is_read_verbatim(db, app_settings, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    project = _project_with_fake_git(db, root)
    head = "a" * 40
    (root / ".git" / "HEAD").write_text(head + "\n", encoding="utf-8")

    result = check_project_health(project.id, app_settings)
    assert result["git_head"] == head


def test_unreadable_git_head_fails_soft(db, app_settings, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    project = _project_with_fake_git(db, root)
    (root / ".git" / "HEAD").write_bytes(b"\xff\xfe\x00")

    result = check_project_health(project.id, app_settings)
    assert result["git_head"] is None


# ---------------------------------------------------------------------------
# Factory defaults
# ---------------------------------------------------------------------------


def test_scheduler_factory_loads_settings_when_omitted(app_settings, monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "load_settings", lambda: app_settings)
    assert isinstance(create_scheduler(), Scheduler)


def test_research_factory_loads_settings_when_omitted(app_settings, monkeypatch) -> None:
    monkeypatch.setattr(research_pipeline, "load_settings", lambda: app_settings)
    assert isinstance(create_research_pipeline(), ResearchPipeline)


def test_ollama_factories_load_settings_when_omitted(app_settings, monkeypatch) -> None:
    monkeypatch.setattr(ollama_module, "load_settings", lambda: app_settings)
    assert isinstance(create_ollama_client(), OllamaClient)
    assert isinstance(create_model_adapter(), ModelAdapter)


def test_is_safe_url_survives_non_strings() -> None:
    assert research_pipeline.is_safe_url(None) is False  # type: ignore[arg-type]
    assert research_pipeline.is_safe_url("https://") is False


# ---------------------------------------------------------------------------
# GitHub cache and read-only placeholders
# ---------------------------------------------------------------------------


def _github(make_settings) -> GitHubIntegration:
    return GitHubIntegration(
        make_settings(
            github_mode="token",
            github_read_only_token="ghp_notarealtokenvalue",
            github_allowed_repositories=["owner/repo"],
        )
    )


def test_repo_metadata_uses_a_fresh_cache_entry(make_settings) -> None:
    github = _github(make_settings)
    github._cache["metadata:owner/repo"] = (time.time(), {"name": "cached"})
    assert github.get_repo_metadata("owner/repo") == {"name": "cached"}


def test_repo_metadata_ignores_an_expired_cache_entry(make_settings) -> None:
    github = _github(make_settings)
    github._cache["metadata:owner/repo"] = (0.0, {"name": "stale"})
    assert github.get_repo_metadata("owner/repo") == {
        "name": "owner/repo",
        "status": "not_fetched",
        "cached": False,
    }


def test_enabled_read_only_endpoints_return_placeholders(make_settings) -> None:
    github = _github(make_settings)
    assert github.get_recent_commits("owner/repo") == []
    assert github.get_issues("owner/repo") == []
    assert github.get_pull_requests("owner/repo") == []
    assert github.get_releases("owner/repo") == []
    assert github.get_ci_status("owner/repo") is None


# ---------------------------------------------------------------------------
# Ollama error handling
# ---------------------------------------------------------------------------


class _CursorResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, get_status=200, get_payload=None, post_payload=None, post_raises=False):
        self.get_status = get_status
        self.get_payload = get_payload or {}
        self.post_payload = post_payload or {}
        self.post_raises = post_raises
        self.posted = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get(self, url):
        return _CursorResponse(self.get_status, self.get_payload)

    def post(self, url, json=None):
        self.posted = True
        if self.post_raises:
            raise RuntimeError("connection reset")
        return _CursorResponse(self.get_status, self.post_payload)


def _client(monkeypatch, fake: _FakeClient) -> None:
    """Kept out of use; integration tests construct clients explicitly."""
    return None


def test_ollama_list_models_handles_error_status(monkeypatch, make_settings) -> None:
    fake = _FakeClient(get_status=500)
    monkeypatch.setattr(ollama_module.httpx, "Client", lambda *a, **k: fake)
    assert OllamaClient(make_settings(ollama_model="llama3")).list_models() == []


def test_ollama_generate_handles_non_string_response(monkeypatch, make_settings) -> None:
    fake = _FakeClient(post_payload={"response": 123})
    monkeypatch.setattr(ollama_module.httpx, "Client", lambda *a, **k: fake)
    assert OllamaClient(make_settings(ollama_model="llama3")).generate("hello") is None


def test_ollama_generate_handles_transport_errors(monkeypatch, make_settings) -> None:
    fake = _FakeClient(post_payload={"response": "ok"}, post_raises=True)
    monkeypatch.setattr(ollama_module.httpx, "Client", lambda *a, **k: fake)
    assert OllamaClient(make_settings(ollama_model="llama3")).generate("hello") is None


def test_ollama_structured_rejects_invalid_json(monkeypatch, make_settings) -> None:
    fake = _FakeClient(post_payload={"response": "{not json}"})
    monkeypatch.setattr(ollama_module.httpx, "Client", lambda *a, **k: fake)
    client = OllamaClient(make_settings(ollama_model="llama3"))
    assert client.generate_structured("q", {"type": "object"}) is None


def test_ollama_generate_structured_needs_an_object(monkeypatch, make_settings) -> None:
    fake = _FakeClient(post_payload={"response": "[1, 2, 3]"})
    monkeypatch.setattr(ollama_module.httpx, "Client", lambda *a, **k: fake)
    client = OllamaClient(make_settings(ollama_model="llama3"))
    assert client.generate_structured("q", {"type": "object"}) is None


def test_model_adapter_recommend_uses_client(make_settings, monkeypatch) -> None:
    class _StubClient:
        def __init__(self):
            self.calls = []

        def generate(self, prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            return "recommendation"

    client = _StubClient()
    adapter = ModelAdapter(client)
    assert adapter.recommend("context") == "recommendation"
    assert "suggest next steps" in client.calls[0][0]


# ---------------------------------------------------------------------------
# OpenCode mock misses
# ---------------------------------------------------------------------------


def test_mock_adapter_returns_none_for_unknown_project(make_settings, tmp_path: Path) -> None:
    adapter = create_mock_adapter(
        make_settings(
            opencode_enabled=True,
            opencode_command="opencode",
            opencode_allowed_worktrees=[tmp_path],
        )
    )
    assert adapter.get_project_metadata("missing") is None


# ---------------------------------------------------------------------------
# Bot helpers and factories
# ---------------------------------------------------------------------------


def test_mock_interaction_shape() -> None:
    interaction = bot_module.MockInteraction(OWNER_ID, GUILD_ID, CHANNEL_ID)
    assert interaction.user.id == OWNER_ID
    assert interaction.guild_id == GUILD_ID
    assert interaction.channel_id == CHANNEL_ID
    assert interaction.client is None
    assert interaction.extras == {}
    assert interaction.response.send_message("hello") is None


def test_create_bot_loads_settings_when_omitted(app_settings, monkeypatch) -> None:
    monkeypatch.setattr(bot_module, "load_settings", lambda: app_settings)
    bot = bot_module.create_bot()
    assert bot.settings is app_settings


def test_create_test_bot_loads_settings_when_omitted(app_settings, monkeypatch) -> None:
    monkeypatch.setattr(bot_module, "load_settings", lambda **kwargs: app_settings)
    bot = bot_module.create_test_bot()
    assert bot.settings is app_settings


def test_bot_factories_fail_without_discord(app_settings, monkeypatch) -> None:
    monkeypatch.setattr(bot_module, "DISCORD_AVAILABLE", False)
    with pytest.raises(RuntimeError, match=r"discord\.py is not installed"):
        bot_module.create_bot(app_settings)
    with pytest.raises(RuntimeError, match=r"discord\.py is not installed"):
        bot_module.create_test_bot(app_settings)


def test_context_helper_tolerates_objects_without_extras() -> None:
    assert commands._context(object()) == (None, None)


def test_root_check_survives_resolution_errors(app_settings, monkeypatch) -> None:
    def _raise(self):
        raise OSError("bad path")

    monkeypatch.setattr(commands.Path, "resolve", _raise)
    assert commands.root_is_allowed("/srv/alpha", app_settings) is False


def test_roadmap_denies_users_without_project_access(db, app_settings) -> None:
    project = repo.upsert_project(
        db, "Alpha", None, str(app_settings.project_allowed_roots[0] / "alpha")
    )
    repo.upsert_discord_mapping(db, project.id, GUILD_ID, CHANNEL_ID, "roadmap")
    interaction = FakeInteraction(app_settings, user_id=OTHER_USER_ID)

    _run(commands.roadmap_command.callback(interaction))

    assert "not authorized" in interaction.last_message


# ---------------------------------------------------------------------------
# Database lifecycle and migration failures
# ---------------------------------------------------------------------------


def test_connection_is_reopened_when_the_database_path_changes(
    app_settings, tmp_path: Path
) -> None:
    first = database._ensure_conn(app_settings)
    other_settings = app_settings.model_copy(update={"database_path": tmp_path / "other.sqlite3"})
    second = database._ensure_conn(other_settings)

    assert first is not second
    assert (tmp_path / "other.sqlite3").exists()
    database.close()


def test_transaction_without_explicit_settings_uses_env(app_settings) -> None:
    database.get_conn()
    assert database.transaction(lambda conn: 42, settings=None) == 42
    database._get_conn_from_settings(app_settings)
    database.close()


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        database._apply_migrations(conn, db_path)
        database._apply_migrations(conn, db_path)
        applied = database._get_applied_migrations(conn)
    finally:
        conn.close()

    assert {"001_initial", "002_schema_constraints"} <= applied


def test_missing_up_function_is_rejected(tmp_path: Path, monkeypatch) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    monkeypatch.setattr(database, "import_module", lambda name: SimpleNamespace())
    with pytest.raises(RuntimeError, match="does not define up"):
        database._apply_migrations(conn, tmp_path / "db.sqlite3")
    conn.close()


def test_failing_migration_is_rolled_back(tmp_path: Path, monkeypatch) -> None:
    def _up(conn) -> None:
        raise RuntimeError("boom")

    conn = sqlite3.connect(tmp_path / "db.sqlite3")
    monkeypatch.setattr(database, "import_module", lambda name: SimpleNamespace(up=_up))
    with pytest.raises(RuntimeError, match="Migration 001_initial failed"):
        database._apply_migrations(conn, tmp_path / "db.sqlite3")
    conn.close()


def test_get_applied_migrations_tolerates_missing_table() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        assert database._get_applied_migrations(conn) == set()
    finally:
        conn.close()


def test_mark_migration_is_best_effort_on_read_only_databases(tmp_path: Path) -> None:
    db_path = tmp_path / "readonly.sqlite3"
    sqlite3.connect(db_path).close()
    readonly = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        database._mark_migration_applied(readonly, "001_initial")  # must not raise
    finally:
        readonly.close()
