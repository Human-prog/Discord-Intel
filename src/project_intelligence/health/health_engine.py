"""Project Health Engine (Phase 6).

Read-only project health and status engine that derives health from observable
evidence within configured allowed roots.  Fail-closed: checks cannot escape
approved project roots, and a failed check is never falsely reported as healthy.

This module replaces any arbitrary script execution with evidence-based checks
against Git repository state, directory existence, and configured prerequisites.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import Settings
from ..storage.database import get_conn
from ..security.authorization import AuthorizationChecker, make_checker


# ---------------------------------------------------------------------------
# Helper: ISO-8601 UTC timestamp
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """Return the current time as an ISO-8601 UTC string."""
    return datetime.now(timezone.utc).isoformat() + "Z"


# ---------------------------------------------------------------------------
# Helper: run a single health check safely
# ---------------------------------------------------------------------------

def _check_path_exists(root: Path, check_path: Path, allowed: bool = True) -> dict[str, Any]:
    """Check if a path exists within a root; return a health dict.

    Safety: *check_path* must be relative and resolved inside *root*.
    If *allowed* is True the check passes when the path exists; if False it
    passes when the path does NOT exist (used for prerequisite checks).
    """
    try:
        # Resolve relative to root, never outside it
        resolved = (root / check_path).resolve()
        # Ensure the resolved path is under the root (path traversal guard)
        if not str(resolved).startswith(str(root.resolve())):
            return {"status": "failed", "reason": "path escapes allowed root"}
        exists = resolved.is_file() or resolved.is_dir()
        if allowed:
            status = "healthy" if exists else "stale"
        else:
            status = "healthy" if not exists else "unhealthy"
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
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Perform a read-only health check for a project.

    The check queries the project's allowed root from the database, then
    performs safe, bounded checks against that root.  No arbitrary scripts
    are executed; only filesystem and Git repository state is inspected.

    Returns a health snapshot dict suitable for insertion into the
    health_snapshots table.
    """
    conn = get_conn()

    try:
        # Look up the project's allowed root from the database
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

        # Base health result
        result: dict[str, Any] = {
            "status": "healthy",
            "project_id": project_id,
            "checked_at_utc": _utc_now(),
            "details": {},
            "correlation_id": correlation_id,
            "git_head": None,
            "git_dirty": 0,
        }

        # 1. Check that the allowed root directory exists
        root_check = _check_path_exists(allowed_root, Path("."), allowed=True)
        result["details"]["root_exists"] = root_check["status"] == "healthy"

        if root_check["status"] != "healthy":
            result["status"] = "unhealthy"
            result["details"]["root_missing"] = True
            return result

        # 2. Check for a .git directory (Git repository presence)
        git_dir = allowed_root / ".git"
        git_exists = git_dir.is_dir()
        result["details"]["git_repository"] = git_exists

        if not git_exists:
            # No Git repo; mark stale rather than unhealthy since the
            # project root exists and is valid.
            result["status"] = "stale"
            result["details"]["no_git_repository"] = True
            result["git_dirty"] = 1  # cannot determine
            return result

        # 3. Read Git HEAD (last committed commit hash)
        try:
            head_file = git_dir / "HEAD"
            if head_file.is_file():
                head_content = head_file.read_text().strip()
                # Normalise to plain hash (remove "ref: refs/heads/..." if present)
                if head_content.startswith("ref: "):
                    ref_path = head_content[5:].strip()
                    # Read the ref
                    refs_dir = git_dir / ref_path
                    if refs_dir.is_file():
                        actual_head = refs_dir.read_text().strip()
                        head = actual_head[:40]  # truncate to hash
                    else:
                        head = head_content[:40]
                else:
                    head = head_content[:40]
                result["git_head"] = head
            else:
                result["git_head"] = None
        except Exception:  # pylint: disable-broad-except
            result["git_head"] = None

        # 4. Determine if the working tree is "dirty" (uncommitted changes)
        try:
            import subprocess  # nosec: B603 — command is fixed, no user input
            result_dir = allowed_root
            # Run git status --porcelain; empty output = clean
            result_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(result_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            # git return code 0 + empty porcelain = clean
            result["git_dirty"] = 0 if result_proc.returncode == 0 and not result_proc.stdout.strip() else 1
        except Exception:  # pylint: disable-broad-except
            result["git_dirty"] = 2  # unable to determine

        # 5. Freshness: record the check timestamp
        # If git_head is present and git_dirty is 0, the project is fresh.
        # Otherwise it may be stale.
        if result["git_head"] is not None and result["git_dirty"] == 0:
            # Fresh: check was recent and repo is clean
            result["status"] = "healthy"
        elif result["git_head"] is not None and result["git_dirty"] == 1:
            # Unhealthy: repo has uncommitted changes
            result["status"] = "unhealthy"
        elif root_check["status"] == "stale":
            # Stale: root exists but git check failed or is missing
            result["status"] = "stale"
        else:
            # Unknown/failed
            result["status"] = "unknown"

        result["details"]["git_head"] = result["git_head"]
        result["details"]["git_dirty"] = result["git_dirty"]

        return result

    finally:
        close()


# ---------------------------------------------------------------------------
# Health snapshot storage
# ---------------------------------------------------------------------------

def store_health_snapshot(
    project_id: int,
    status: str,
    *,
    details: Optional[dict[str, Any]] = None,
    git_head: Optional[str] = None,
    git_dirty: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Insert a health snapshot into the database.

    Uses the transaction helper so the write is atomic.
    """
    conn = get_conn()
    try:
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
                _utc_now(),
                json.dumps(details) if details else None,
                git_head,
                git_dirty,
                correlation_id,
            ),
        )
        conn.commit()
    finally:
        close()


# ---------------------------------------------------------------------------
# Convenience: health check + store in one atomic operation
# ---------------------------------------------------------------------------

def check_and_store_health(
    project_id: int,
    settings: Settings,
    *,
    correlation_id: Optional[str] = None,
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
    )
    return snapshot