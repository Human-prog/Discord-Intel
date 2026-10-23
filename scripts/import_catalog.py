#!/usr/bin/env python3
"""Import a workstation project catalog into the DPI SQLite database.

Usage (on the server):

    python scripts/import_catalog.py --catalog catalog.json

The catalog is produced by ``scripts/catalog_projects.py`` on the machine that
owns the projects.  Import is idempotent: a project is matched by its stable
``catalog_key`` (falling back to the recorded path), and Git work items are
matched by commit hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from project_intelligence.storage import repositories as repo
from project_intelligence.storage.database import get_conn

SCHEMA_VERSION = 1
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STATUS = {"active", "idle", "dormant", "unknown", "archived"}
_ALLOWED_PRIORITY = {"high", "medium", "low", "agent", "idea", None}
_ALLOWED_WORK_TYPES = {"commit", "note", "task", "milestone", "manual"}


class CatalogError(ValueError):
    """Invalid catalog input; the message never includes file contents."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _is_absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _valid_iso(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogError("timestamp is not valid ISO-8601") from exc
    return text


def _require_str(value: object, field: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise CatalogError(f"{field} must not be empty")
    if len(text) > max_length:
        raise CatalogError(f"{field} exceeds {max_length} characters")
    return text


def _optional_str(value: object, field: str, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalogError(f"{field} must be a string or null")
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise CatalogError(f"{field} exceeds {max_length} characters")
    return text


def _string_list(value: object, field: str, *, max_items: int, max_length: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CatalogError(f"{field} must be a list")
    if len(value) > max_items:
        raise CatalogError(f"{field} has more than {max_items} entries")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise CatalogError(f"{field} entries must be strings")
        text = item.strip()
        if text and len(text) <= max_length:
            result.append(text)
    return result[:max_items]


def _dict(value: object, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CatalogError(f"{field} must be an object")
    return value


def _validate_project(raw: object, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CatalogError(f"projects[{index}] must be an object")
    catalog_key = _require_str(
        raw.get("catalog_key"), f"projects[{index}].catalog_key", max_length=64
    )
    if not _HEX64_RE.match(catalog_key):
        raise CatalogError(f"projects[{index}].catalog_key must be a lowercase SHA-256 hex digest")
    name = _require_str(raw.get("name"), f"projects[{index}].name", max_length=200)
    local_path = _require_str(
        raw.get("local_path"), f"projects[{index}].local_path", max_length=1000
    )
    if not _is_absolute_path(local_path):
        raise CatalogError(f"projects[{index}].local_path must be absolute")
    description = _optional_str(
        raw.get("description"), f"projects[{index}].description", max_length=4000
    )
    repo_url = _optional_str(raw.get("repo_url"), f"projects[{index}].repo_url", max_length=1000)
    if repo_url is not None and not repo_url.startswith(("https://", "http://")):
        raise CatalogError(f"projects[{index}].repo_url must be an HTTP(S) URL")
    status = str(raw.get("catalog_status") or "unknown").strip().lower()
    if status not in _ALLOWED_STATUS:
        status = "unknown"
    priority = raw.get("priority")
    priority_text = None if priority is None else str(priority).strip().lower()
    if priority_text not in _ALLOWED_PRIORITY:
        priority_text = None
    category = _optional_str(raw.get("category"), f"projects[{index}].category", max_length=200)
    tech_stack = _string_list(
        raw.get("tech_stack"),
        f"projects[{index}].tech_stack",
        max_items=20,
        max_length=80,
    )
    metadata = _dict(raw.get("metadata"), f"projects[{index}].metadata")
    relative_path = _optional_str(
        raw.get("relative_path"), f"projects[{index}].relative_path", max_length=1000
    )
    markers = _string_list(
        raw.get("markers"),
        f"projects[{index}].markers",
        max_items=30,
        max_length=80,
    )
    last_activity = _valid_iso(raw.get("last_activity_utc"))

    work_items_raw = raw.get("work_items") or []
    if not isinstance(work_items_raw, list):
        raise CatalogError(f"projects[{index}].work_items must be a list")
    if len(work_items_raw) > 500:
        raise CatalogError(f"projects[{index}].work_items has more than 500 entries")
    work_items: list[dict[str, Any]] = []
    seen_external: set[str] = set()
    for item_index, item in enumerate(work_items_raw):
        if not isinstance(item, dict):
            raise CatalogError(f"projects[{index}].work_items[{item_index}] must be an object")
        title = _require_str(
            item.get("title"),
            f"projects[{index}].work_items[{item_index}].title",
            max_length=500,
        )
        source = str(item.get("source") or "git").strip().lower()
        if source not in {"git", "manual", "import"}:
            source = "import"
        work_type = str(item.get("work_type") or "commit").strip().lower()
        if work_type not in _ALLOWED_WORK_TYPES:
            work_type = "manual"
        external_id = _optional_str(
            item.get("external_id"),
            f"projects[{index}].work_items[{item_index}].external_id",
            max_length=200,
        )
        if external_id is not None:
            if external_id in seen_external:
                continue
            seen_external.add(external_id)
        occurred = _valid_iso(item.get("occurred_at_utc"))
        item_status = str(item.get("status") or "done").strip().lower()
        if item_status not in {"done", "active", "planned", "blocked"}:
            item_status = "done"
        body = _optional_str(
            item.get("body"),
            f"projects[{index}].work_items[{item_index}].body",
            max_length=4000,
        )
        work_items.append(
            {
                "work_type": work_type,
                "title": title,
                "body": body,
                "status": item_status,
                "source": source,
                "external_id": external_id,
                "occurred_at_utc": occurred,
                "metadata": _dict(
                    item.get("metadata"),
                    f"projects[{index}].work_items[{item_index}].metadata",
                ),
            }
        )

    return {
        "catalog_key": catalog_key,
        "name": name,
        "local_path": local_path,
        "relative_path": relative_path,
        "description": description,
        "repo_url": repo_url,
        "tech_stack": tech_stack,
        "category": category,
        "priority": priority_text,
        "catalog_status": status,
        "last_activity_utc": last_activity,
        "markers": markers,
        "metadata": metadata,
        "work_items": work_items,
    }


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise CatalogError(
            f"could not read catalog: {exc.strerror or type(exc).__name__}"
        ) from None
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"catalog is not valid JSON: {type(exc).__name__}") from None
    if not isinstance(data, dict):
        raise CatalogError("catalog root must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise CatalogError(f"catalog schema_version must be {SCHEMA_VERSION}")
    projects_raw = data.get("projects")
    if not isinstance(projects_raw, list):
        raise CatalogError("catalog.projects must be a list")
    if len(projects_raw) > 1000:
        raise CatalogError("catalog has more than 1000 projects")
    projects = [_validate_project(item, index) for index, item in enumerate(projects_raw)]
    keys: set[str] = set()
    paths: set[str] = set()
    for project in projects:
        if project["catalog_key"] in keys:
            raise CatalogError(f"duplicate catalog_key: {project['catalog_key']}")
        keys.add(project["catalog_key"])
        lowered_path = project["local_path"].lower()
        if lowered_path in paths:
            raise CatalogError(f"duplicate local_path: {project['local_path']}")
        paths.add(lowered_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _valid_iso(data.get("generated_at_utc")),
        "root": data.get("root"),
        "projects": projects,
        "checksum": hashlib.sha256(raw_bytes).hexdigest(),
        "source_name": path.name,
    }


def import_catalog(catalog: dict[str, Any], *, dry_run: bool = False) -> dict[str, int]:
    projects = catalog["projects"]
    project_count = 0
    work_item_count = 0
    if dry_run:
        return {
            "projects": len(projects),
            "work_items": sum(len(project["work_items"]) for project in projects),
        }

    conn = get_conn()
    try:
        for project in projects:
            record = repo.upsert_catalog_project(
                conn,
                catalog_key=project["catalog_key"],
                name=project["name"],
                description=project["description"],
                local_path=project["local_path"],
                repo_url=project["repo_url"],
                tech_stack_json=json.dumps(project["tech_stack"], ensure_ascii=False)
                if project["tech_stack"]
                else None,
                category=project["category"],
                priority=project["priority"],
                catalog_status=project["catalog_status"],
                last_activity_utc=project["last_activity_utc"],
                metadata_json=json.dumps(
                    {
                        **project["metadata"],
                        "relative_path": project["relative_path"],
                        "markers": project["markers"],
                    },
                    ensure_ascii=False,
                ),
                source="catalog",
                monitored=0,
            )
            project_count += 1
            for item in project["work_items"]:
                repo.upsert_work_item(
                    conn,
                    record.id,
                    item["work_type"],
                    item["title"],
                    body=item["body"],
                    status=item["status"],
                    source=item["source"],
                    external_id=item["external_id"],
                    occurred_at_utc=item["occurred_at_utc"],
                    metadata_json=json.dumps(item["metadata"], ensure_ascii=False)
                    if item["metadata"]
                    else None,
                )
                work_item_count += 1
        repo.record_catalog_import(
            conn,
            source_name=str(catalog.get("source_name") or "catalog.json"),
            source_checksum=str(catalog["checksum"]),
            project_count=project_count,
            work_item_count=work_item_count,
            metadata_json=json.dumps(
                {
                    "generated_at_utc": catalog.get("generated_at_utc"),
                    "root": catalog.get("root"),
                    "imported_at_utc": _utc_now(),
                },
                ensure_ascii=False,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"projects": project_count, "work_items": work_item_count}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True, help="Catalog JSON to import")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog(args.catalog)
        counts = import_catalog(catalog, dry_run=args.dry_run)
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - database failure boundary
        print(f"error: import failed ({type(exc).__name__})", file=sys.stderr)
        return 1

    verb = "validated" if args.dry_run else "imported"
    print(
        f"{verb} {counts['projects']} projects and {counts['work_items']} work items "
        f"from {args.catalog}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
