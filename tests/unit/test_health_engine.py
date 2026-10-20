"""Health engine tests (Phase 6): fail-closed, read-only checks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from project_intelligence.health import health_engine
from project_intelligence.health.health_engine import (
    _check_path_exists,
    check_and_store_health,
    check_project_health,
    store_health_snapshot,
)
from project_intelligence.storage import repositories as repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")

_GIT = shutil.which("git") or "git"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argument list in tests only
        [_GIT, *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-m",
        "init",
    )
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _project(db, root: Path):
    return repo.upsert_project(db, "Alpha", None, str(root))


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def test_path_check_allows_paths_under_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")

    result = _check_path_exists(root, Path("file.txt"))
    assert result["status"] == "healthy"
    assert result["exists"] is True


def test_path_check_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("x", encoding="utf-8")

    result = _check_path_exists(root, Path("../outside.txt"))
    assert result["status"] == "failed"
    assert "escapes allowed root" in result["reason"]


def test_path_check_reports_missing_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    result = _check_path_exists(root, Path("missing"))
    assert result["status"] == "stale"
    assert result["exists"] is False


def test_path_check_inverted_expectation(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    assert _check_path_exists(root, Path("missing"), allowed=False)["status"] == "healthy"
    (root / "present").write_text("x", encoding="utf-8")
    assert _check_path_exists(root, Path("present"), allowed=False)["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# Project health
# ---------------------------------------------------------------------------


def test_unknown_project_is_unknown(app_settings) -> None:
    result = check_project_health(999_999, app_settings)
    assert result["status"] == "unknown"
    assert result["details"] == "project not found"


def test_missing_root_is_unhealthy(db, app_settings, tmp_path: Path) -> None:
    project = _project(db, tmp_path / "does-not-exist")
    result = check_project_health(project.id, app_settings)
    assert result["status"] == "unhealthy"
    assert result["details"]["root_missing"] is True


def test_directory_without_git_is_stale(db, app_settings, tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    project = _project(db, root)

    result = check_project_health(project.id, app_settings)
    assert result["status"] == "stale"
    assert result["details"]["git_repository"] is False
    assert result["git_dirty"] == 1


def test_clean_repository_is_healthy(db, app_settings, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    head = _init_repo(root)
    project = _project(db, root)

    result = check_project_health(project.id, app_settings)
    assert result["status"] == "healthy"
    assert result["git_dirty"] == 0
    assert result["git_head"] == head
    assert result["details"]["root_exists"] is True


def test_dirty_repository_is_unhealthy(db, app_settings, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    (root / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")
    project = _project(db, root)

    result = check_project_health(project.id, app_settings)
    assert result["git_dirty"] == 1
    assert result["status"] == "unhealthy"


def test_missing_git_binary_fails_closed(db, app_settings, tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    project = _project(db, root)
    monkeypatch.setattr(health_engine.shutil, "which", lambda _name: None)

    result = check_project_health(project.id, app_settings)
    assert result["git_dirty"] == 2
    assert result["status"] == "unknown"


def test_git_timeout_fails_closed(db, app_settings, tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    project = _project(db, root)

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git status", timeout=1)

    monkeypatch.setattr(health_engine.subprocess, "run", _timeout)
    result = check_project_health(project.id, app_settings)
    assert result["git_dirty"] == 2
    assert result["status"] == "unknown"


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------


def test_store_health_snapshot_defaults_git_dirty_to_zero(db) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    store_health_snapshot(project.id, "healthy")

    row = db.execute(
        "SELECT status, git_dirty, details FROM health_snapshots WHERE project_id = ?",
        (project.id,),
    ).fetchone()
    assert row[0] == "healthy"
    assert row[1] == 0
    assert row[2] is None


def test_check_and_store_health_persists_snapshot(db, app_settings, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    project = _project(db, root)

    result = check_and_store_health(project.id, app_settings, correlation_id="corr-1")
    assert result["status"] == "healthy"

    latest = repo.get_latest_health_snapshot(db, project.id)
    assert latest is not None
    assert latest[0] == "healthy"
    assert latest[1].endswith("Z")

    stored = db.execute(
        "SELECT correlation_id, git_dirty FROM health_snapshots WHERE project_id = ?",
        (project.id,),
    ).fetchone()
    assert stored[0] == "corr-1"
    assert stored[1] == 0
