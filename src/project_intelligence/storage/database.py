"""SQLite connection and transaction layer (Phase 4).

Provides a single, thread-aware connection wrapper that:
- Creates the database and applies pending migrations on first use.
- Centralises transactions (commit/rollback) so callers don't have to.
- Enforces that no raw SQL strings carrying arbitrary commands reach the
  persistence layer.
- Keeps credentials out of ordinary application tables.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

from ..config import Settings

_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None
_CONN_PATH: Path | None = None


def _ensure_conn(settings: Settings) -> sqlite3.Connection:
    """Create or return the active SQLite connection, applying pending migrations."""
    global _CONN, _CONN_PATH

    with _LOCK:
        db_path = Path(settings.database_path) if settings.database_path else Path("data/db.sqlite3")
        if _CONN is not None and db_path == _CONN_PATH:
            return _CONN

        # Settings or database path changed: close the previous connection.
        if _CONN is not None:
            _CONN.close()
            _CONN = None

        db_path.parent.mkdir(parents=True, exist_ok=True)

        _CONN = sqlite3.connect(str(db_path), check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _CONN_PATH = db_path

        _apply_migrations(_CONN, db_path)

        return _CONN


def _apply_migrations(conn: sqlite3.Connection, db_path: Path) -> None:
    """Run versioned migrations; create the schema_migrations table if needed."""
    _create_schema_migrations_table(conn)

    # Read which migrations have already been applied.
    applied = _get_applied_migrations(conn)

    # Discover available migration files in the migrations directory.
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.is_dir():
        return

    migration_files = sorted(migrations_dir.glob("*.py"))

    for mf in migration_files:
        # Migration name is the stem (e.g. "001_initial").
        name = mf.stem
        if name in applied:
            continue
        # Each migration module must expose an `up` function.
        mod = import_module(f"project_intelligence.storage.migrations.{name}")
        up_fn = getattr(mod, "up", None)
        if up_fn is None:
            raise RuntimeError(f"Migration {name} does not define up(conn)")

        try:
            up_fn(conn)
            _mark_migration_applied(conn, name)
        except Exception as exc:
            # Do not leave a partially-applied migration recorded.
            conn.rollback()
            raise RuntimeError(f"Migration {name} failed: {exc}") from exc


def _create_schema_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the table that tracks which migrations have been applied."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT NOT NULL UNIQUE,
            applied_at_utc TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _get_applied_migrations(conn: sqlite3.Connection) -> set[str]:
    """Return the set of migration names already recorded."""
    try:
        rows = conn.execute("SELECT migration_name FROM schema_migrations").fetchall()
        return {row["migration_name"] for row in rows}
    except sqlite3.OperationalError:
        return set()


def _mark_migration_applied(conn: sqlite3.Connection, name: str) -> None:
    """Record that a migration has been applied (best-effort; use within a txn)."""
    try:
        conn.execute(
            "INSERT INTO schema_migrations (migration_name, applied_at_utc) VALUES (?, ?)",
            (name, datetime.now(UTC).isoformat().replace("+00:00", "Z")),
        )
        conn.commit()
    except sqlite3.OperationalError:
        # Table might not exist yet; caller should ensure it does.
        pass


def get_conn() -> sqlite3.Connection:
    """Return the active connection, raising if none exists yet."""
    from ..config import load_settings

    settings = load_settings()
    return _ensure_conn(settings)


def close() -> None:
    """Close the connection (call at process shutdown)."""
    global _CONN, _CONN_PATH
    if _CONN is not None:
        _CONN.close()
        _CONN = None
        _CONN_PATH = None


def transaction(func: Any, *, settings: Any = None) -> Any:
    """Execute *func* within a transaction using the active connection.

    If *settings* is provided, the connection is freshly ensured for those
    settings; otherwise the global active connection is used.

    The function receives the connection as its first argument and must return
    a value.  On success the transaction is committed; on any exception it is
    rolled back and the exception re-raised.
    """

    conn = _ensure_conn(settings) if settings else _get_conn_from_settings(settings)

    try:
        result = func(conn)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _get_conn_from_settings(settings: Any) -> sqlite3.Connection:
    """Helper for transaction()."""
    from ..config import load_settings

    if settings is None:
        settings = load_settings()
    return _ensure_conn(settings)
