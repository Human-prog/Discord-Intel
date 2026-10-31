#!/usr/bin/env python3
"""Consistent SQLite backup script for Discord Project Intelligence.

Uses SQLite's online backup API (VACUUM INTO) to create a consistent
snapshot of the database without locking it for long periods.

Usage:
    python scripts/backup_db.py [--output DIR] [--retention DAYS]

Environment:
    DPI_DATA_DIR - Path to the application data directory (default: /var/lib/dpi/data)
    DPI_BACKUP_DIR - Path to backup directory (default: /var/backups/dpi)

Exit codes:
    0 - Success
    1 - Error (see stderr)
"""

from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_RETENTION_DAYS = 7


def get_db_path() -> Path:
    """Return the database path from environment or default."""
    data_dir = os.environ.get("DPI_DATA_DIR", "/var/lib/dpi/data")
    db_path = Path(data_dir) / "db.sqlite3"
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    return db_path


def backup_database(db_path: Path, backup_dir: Path) -> Path:
    """Create a consistent backup using SQLite's online backup API."""
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    backup_name = f"db_{timestamp}.sqlite3"
    backup_path = backup_dir / backup_name

    # Use SQLite's online backup API for consistency
    conn = sqlite3.connect(str(db_path))
    try:
        # VACUUM INTO creates a consistent snapshot
        conn.execute(f"VACUUM INTO '{backup_path}'")
        conn.commit()
    finally:
        conn.close()

    # Verify backup integrity
    verify_conn = sqlite3.connect(str(backup_path))
    try:
        result = verify_conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            print(f"ERROR: Backup integrity check failed: {result[0]}", file=sys.stderr)
            backup_path.unlink(missing_ok=True)
            sys.exit(1)
    finally:
        verify_conn.close()

    # Set permissions (owner only)
    backup_path.chmod(0o600)

    print(f"Backup created: {backup_path}")
    print(f"Size: {backup_path.stat().st_size} bytes")
    return backup_path


def cleanup_old_backups(backup_dir: Path, retention_days: int) -> None:
    """Remove backups older than the retention period."""
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=retention_days)
    removed = 0
    for backup_file in backup_dir.glob("db_*.sqlite3"):
        try:
            mtime = datetime.datetime.fromtimestamp(backup_file.stat().st_mtime, tz=datetime.UTC)
            if mtime < cutoff:
                backup_file.unlink()
                removed += 1
        except Exception:  # noqa: S110 - best-effort cleanup of unreadable files
            pass
    if removed:
        print(f"Removed {removed} old backup(s) older than {retention_days} days")


def main() -> int:
    parser = argparse.ArgumentParser(description="Consistent SQLite backup")
    parser.add_argument("--output", type=Path, default=None, help="Backup directory")
    parser.add_argument("--retention", type=int, default=DEFAULT_RETENTION_DAYS, help="Retention days")
    args = parser.parse_args()

    db_path = get_db_path()
    backup_dir = args.output or Path(os.environ.get("DPI_BACKUP_DIR", "/var/backups/dpi"))
    backup_database(db_path, backup_dir)
    cleanup_old_backups(backup_dir, args.retention)
    return 0


if __name__ == "__main__":
    sys.exit(main())
