"""Project Health Engine (Phase 6).

Read-only project health and status engine that derives health from observable
evidence within configured allowed roots.  Fail-closed: checks cannot escape
approved project roots, and a failed check is never falsely reported as healthy.

This module replaces any arbitrary script execution with evidence-based checks
against Git repository state, directory existence, and configured prerequisites.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..storage.database import get_conn

# ---------------------------------------------------------------------------
# Helper: ISO-8601 UTC timestamp
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    """Return the current time as an ISO-8601 UTC string."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Helper: run a single health check safely
# ---------------------------------------------------------------------------


def _check_path_exists(root: Path, check_path: Path, allowed: bool = True) -> dict[str, Any]:
    """Check if a path exists within a root; return a health dict.

    Safety: *check_path* must resolve inside *root*.  If *allowed* is True the
    check passes when the path exists; if False it passes when the path does
    NOT exist (used for prerequisite checks).
    """
    try:
        resolved = (root / check_path).resolve()
        # Path traversal guard: the resolved path must stay under the root.
        if not resolved.is_relative_to(root.resolve()):
            return {"status": "failed", "reason": "path escapes allowed root"}
        exists = resolved.is_file() or resolved.is_dir()
        status = ("healthy" if exists else "stale") if allowed else "healthy" if not exists else "unhealthy"
        return {"status": status, "path": str(resolved), "exists": exists}
    except Exception as exc:  # pylint: disable-broad-except
        return {"status": "failed", "reason": str(exc)}


# ---------------------------------------------------------------------------
# Project health check
# ---------------------------------------------------------------------------


def check_project_health(
    project_id: int,
    settings: Settings,
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Perform a read-only health check for a project.

    The check queries the project's allowed root from the database, then
    performs safe, bounded checks against that root.  No arbitrary scripts are
    executed; only filesystem and Git repository state is inspected.

    Returns a health snapshot dict suitable for insertion into the
    health_snapshots table.
    """
    del settings  # reserved for future policy knobs; connection owns settings
    conn = get_conn()

    row = conn.execute(
        "SELECT allowed_root FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()

    if row is None:
        return {
            "status": "unknown",
            "project_id": project_id,
            "checked_at_utc": _utc_now(),
            "details": "project not found",
            "correlation_id": correlation_id,
        }

    allowed_root = Path(row[0])

    result: dict[str, Any] = {
        "status": "healthy",
        "project_id": project_id,
        "checked_at_utc": _utc_now(),
        "details": {},
        "correlation_id": correlation_id,
        "git_head": None,
        "git_dirty": 0,
    }
    details: dict[str, Any] = result["details"]

    # 1. The allowed root must exist and be reachable.
    root_check = _check_path_exists(allowed_root, Path("."), allowed=True)
    details["root_exists"] = root_check["status"] == "healthy"
    if root_check["status"] != "healthy":
        result["status"] = "unhealthy"
        details["root_missing"] = True
        return result

    # 2. A Git repository is expected but not mandatory.
    git_dir = allowed_root / ".git"
    git_exists = git_dir.is_dir()
    details["git_repository"] = git_exists
    if not git_exists:
        # Root exists and is valid, but without Git we cannot derive freshness.
        result["status"] = "stale"
        details["no_git_repository"] = True
        result["git_dirty"] = 1  # cannot determine
        return result

    # 3. Read Git HEAD (last committed commit hash) directly from the repo.
    try:
        head_file = git_dir / "HEAD"
        if head_file.is_file():
            head_content = head_file.read_text(encoding="utf-8").strip()
            if head_content.startswith("ref: "):
                ref_path = head_content[5:].strip()
                refs_file = git_dir / ref_path
                if refs_file.is_file():
                    result["git_head"] = refs_file.read_text(encoding="utf-8").strip()[:40]
                else:
                    result["git_head"] = head_content[:40]
            else:
                result["git_head"] = head_content[:40]
    except Exception:  # pylint: disable-broad-except
        result["git_head"] = None

    # 4. Determine whether the working tree is dirty (uncommitted changes).
    try:
        git_bin = shutil.which("git")
        if git_bin is None:
            raise FileNotFoundError("git executable not found")
        proc = subprocess.run(  # noqa: S603 - fixed argument list, no user input
            [git_bin, "status", "--porcelain"],
            cwd=str(allowed_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        result["git_dirty"] = 0 if proc.returncode == 0 and not proc.stdout.strip() else 1
    except Exception:  # pylint: disable-broad-except
        result["git_dirty"] = 2  # unable to determine

    # 5. Derive overall status from observable Git state.
    if result["git_head"] is not None and result["git_dirty"] == 0:
        result["status"] = "healthy"
    elif result["git_head"] is not None and result["git_dirty"] == 1:
        result["status"] = "unhealthy"
    else:
        result["status"] = "unknown"

    details["git_head"] = result["git_head"]
    details["git_dirty"] = result["git_dirty"]
    return result


# ---------------------------------------------------------------------------
# Health snapshot storage
# ---------------------------------------------------------------------------


def store_health_snapshot(
    project_id: int,
    status: str,
    *,
    details: dict[str, Any] | str | None = None,
    git_head: str | None = None,
    git_dirty: int | None = None,
    correlation_id: str | None = None,
    checked_at_utc: str | None = None,
) -> None:
    """Insert a health snapshot into the database (single atomic write)."""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO health_snapshots
            (project_id, status, checked_at_utc, details, git_head, git_dirty, correlation_id)
        VALUES
            (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            status,
            checked_at_utc or _utc_now(),
            json.dumps(details) if details is not None else None,
            git_head,
            0 if git_dirty is None else git_dirty,
            correlation_id,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Convenience: health check + store in one operation
# ---------------------------------------------------------------------------


def check_and_store_health(
    project_id: int,
    settings: Settings,
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Run a health check and persist the snapshot; returns the snapshot dict."""
    snapshot = check_project_health(project_id, settings, correlation_id=correlation_id)
    store_health_snapshot(
        project_id=project_id,
        status=snapshot["status"],
        details=snapshot.get("details"),
        git_head=snapshot.get("git_head"),
        git_dirty=snapshot.get("git_dirty"),
        correlation_id=correlation_id,
        checked_at_utc=snapshot["checked_at_utc"],
    )
    return snapshot
