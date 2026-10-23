"""Validation and idempotent import for workstation project catalogs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from project_intelligence.storage import repositories as repo
from scripts.import_catalog import (
    CatalogError,
    _dict,
    _is_absolute_path,
    _optional_str,
    _require_str,
    _string_list,
    _utc_now,
    _valid_iso,
    _validate_project,
    import_catalog,
    load_catalog,
    main,
)

KEY_A = "a" * 64
KEY_B = "b" * 64


def _work_item(**overrides):
    item = {
        "work_type": "commit",
        "title": "Initial commit",
        "body": "did the thing",
        "status": "done",
        "source": "git",
        "external_id": "c" * 40,
        "occurred_at_utc": "2026-10-20T00:00:00Z",
        "metadata": {"author": "A"},
    }
    item.update(overrides)
    return item


def _project(**overrides):
    project = {
        "catalog_key": KEY_A,
        "name": "Alpha",
        "local_path": "C:\\Projects\\Alpha",
        "relative_path": "Alpha",
        "description": "A project",
        "repo_url": "https://example.com/alpha",
        "tech_stack": ["Python", "FastAPI"],
        "category": "01 - High Priority Projects",
        "priority": "high",
        "catalog_status": "active",
        "last_activity_utc": "2026-10-20T00:00:00Z",
        "markers": ["pyproject.toml"],
        "metadata": {"branch": "main"},
        "work_items": [_work_item()],
    }
    project.update(overrides)
    return project


def _catalog(projects=None, **overrides):
    selected = projects if projects is not None else [_project()]
    catalog = {
        "schema_version": 1,
        "generated_at_utc": "2026-10-20T00:00:00Z",
        "root": "C:\\Projects",
        "projects": selected,
        "checksum": hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest(),
        "source_name": "catalog.json",
    }
    catalog.update(overrides)
    return catalog


def _write(tmp_path: Path, payload: object, name: str = "catalog.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_helper_validation_edges(tmp_path) -> None:
    assert _utc_now().endswith("Z")
    assert _is_absolute_path("C:\\x") is True
    assert _is_absolute_path("/srv/x") is True
    assert _is_absolute_path("relative/x") is False
    assert _valid_iso(None) is None
    assert _valid_iso("") is None
    assert _valid_iso("2026-10-20T00:00:00Z") == "2026-10-20T00:00:00Z"
    with pytest.raises(CatalogError, match="ISO-8601"):
        _valid_iso("not-a-date")

    with pytest.raises(CatalogError, match="must be a string"):
        _require_str(1, "x", max_length=10)
    with pytest.raises(CatalogError, match="must not be empty"):
        _require_str("  ", "x", max_length=10)
    with pytest.raises(CatalogError, match="exceeds"):
        _require_str("x" * 11, "x", max_length=10)
    assert _require_str("  ok  ", "x", max_length=10) == "ok"

    assert _optional_str(None, "x", max_length=10) is None
    with pytest.raises(CatalogError, match="string or null"):
        _optional_str(1, "x", max_length=10)
    assert _optional_str("  ", "x", max_length=10) is None
    with pytest.raises(CatalogError, match="exceeds"):
        _optional_str("x" * 11, "x", max_length=10)
    assert _optional_str(" ok ", "x", max_length=10) == "ok"

    assert _string_list(None, "x", max_items=2, max_length=5) == []
    with pytest.raises(CatalogError, match="must be a list"):
        _string_list("x", "x", max_items=2, max_length=5)
    with pytest.raises(CatalogError, match="more than"):
        _string_list(["a", "b", "c"], "x", max_items=2, max_length=5)
    with pytest.raises(CatalogError, match="entries must be strings"):
        _string_list([1], "x", max_items=2, max_length=5)
    assert _string_list([" a ", "", "toolongvalue"], "x", max_items=3, max_length=5) == ["a"]

    assert _dict(None, "x") == {}
    with pytest.raises(CatalogError, match="must be an object"):
        _dict([], "x")
    assert _dict({"a": 1}, "x") == {"a": 1}


def test_validate_project_defaults_and_normalization() -> None:
    project = _validate_project(
        {
            "catalog_key": KEY_A,
            "name": "  Alpha  ",
            "local_path": "/srv/alpha",
            "catalog_status": "not-a-status",
            "priority": "urgent",
        },
        0,
    )
    assert project["name"] == "Alpha"
    assert project["catalog_status"] == "unknown"
    assert project["priority"] is None
    assert project["description"] is None
    assert project["tech_stack"] == []
    assert project["markers"] == []
    assert project["metadata"] == {}
    assert project["work_items"] == []
    assert project["last_activity_utc"] is None


def test_validate_project_rejects_bad_shapes() -> None:
    with pytest.raises(CatalogError, match="must be an object"):
        _validate_project("x", 0)
    with pytest.raises(CatalogError, match="catalog_key"):
        _validate_project({**_project(), "catalog_key": "short"}, 0)
    with pytest.raises(CatalogError, match="name"):
        _validate_project({**_project(), "name": ""}, 0)
    with pytest.raises(CatalogError, match="local_path must be absolute"):
        _validate_project({**_project(), "local_path": "relative"}, 0)
    with pytest.raises(CatalogError, match="repo_url must be an HTTP"):
        _validate_project({**_project(), "repo_url": "git@example.com:a/b.git"}, 0)
    with pytest.raises(CatalogError, match="description"):
        _validate_project({**_project(), "description": 1}, 0)
    with pytest.raises(CatalogError, match="category"):
        _validate_project({**_project(), "category": 1}, 0)
    with pytest.raises(CatalogError, match="tech_stack"):
        _validate_project({**_project(), "tech_stack": "Python"}, 0)
    with pytest.raises(CatalogError, match="markers"):
        _validate_project({**_project(), "markers": "pyproject.toml"}, 0)
    with pytest.raises(CatalogError, match="metadata"):
        _validate_project({**_project(), "metadata": "x"}, 0)
    with pytest.raises(CatalogError, match="work_items must be a list"):
        _validate_project({**_project(), "work_items": "x"}, 0)
    with pytest.raises(CatalogError, match="more than 500"):
        _validate_project({**_project(), "work_items": [{}] * 501}, 0)
    with pytest.raises(CatalogError, match="must be an object"):
        _validate_project({**_project(), "work_items": ["x"]}, 0)
    with pytest.raises(CatalogError, match="title"):
        _validate_project({**_project(), "work_items": [{"title": ""}]}, 0)
    with pytest.raises(CatalogError, match="body"):
        _validate_project({**_project(), "work_items": [_work_item(body=1)]}, 0)
    with pytest.raises(CatalogError, match="metadata"):
        _validate_project({**_project(), "work_items": [_work_item(metadata="x")]}, 0)


def test_validate_project_normalizes_work_items() -> None:
    project = _validate_project(
        _project(
            work_items=[
                _work_item(source="email", work_type="email", status="weird", external_id="d" * 40),
                _work_item(external_id="d" * 40, title="duplicate skipped"),
            ]
        ),
        0,
    )
    assert len(project["work_items"]) == 1
    item = project["work_items"][0]
    assert item["source"] == "import"
    assert item["work_type"] == "manual"
    assert item["status"] == "done"
    assert item["external_id"] == "d" * 40


def test_load_catalog_success(tmp_path) -> None:
    path = _write(tmp_path, _catalog())
    catalog = load_catalog(path)
    assert catalog["source_name"] == "catalog.json"
    assert catalog["schema_version"] == 1
    assert catalog["generated_at_utc"] == "2026-10-20T00:00:00Z"
    assert catalog["root"] == "C:\\Projects"
    assert catalog["projects"][0]["name"] == "Alpha"
    assert catalog["checksum"] == __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def test_load_catalog_rejects_invalid_files(tmp_path) -> None:
    with pytest.raises(CatalogError, match="could not read"):
        load_catalog(tmp_path / "missing.json")

    bad_utf8 = tmp_path / "bad-utf8.json"
    bad_utf8.write_bytes(b"\xff\xfe")
    with pytest.raises(CatalogError, match="not valid JSON"):
        load_catalog(bad_utf8)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{bad", encoding="utf-8")
    with pytest.raises(CatalogError, match="not valid JSON"):
        load_catalog(bad_json)

    for payload, message in (
        ([], "root must be an object"),
        (_catalog(schema_version=2), "schema_version"),
        (_catalog(projects="x"), "projects must be a list"),
    ):
        with pytest.raises(CatalogError, match=message):
            load_catalog(_write(tmp_path, payload))

    with pytest.raises(CatalogError, match="more than 1000"):
        load_catalog(_write(tmp_path, _catalog(projects=[{}] * 1001)))


def test_load_catalog_rejects_duplicate_keys_and_paths(tmp_path) -> None:
    with pytest.raises(CatalogError, match="duplicate catalog_key"):
        load_catalog(
            _write(
                tmp_path,
                _catalog(
                    projects=[
                        _project(),
                        _project(name="Beta", local_path="C:\\Projects\\Beta"),
                    ]
                ),
            )
        )
    with pytest.raises(CatalogError, match="duplicate local_path"):
        load_catalog(
            _write(
                tmp_path,
                _catalog(
                    projects=[
                        _project(),
                        _project(catalog_key=KEY_B, name="Beta", local_path="c:\\projects\\alpha"),
                    ]
                ),
            )
        )


def test_import_catalog_dry_run_and_real(db, app_settings, monkeypatch) -> None:
    first = _catalog(
        projects=[
            _project(
                tech_stack=[],
                metadata={},
                work_items=[_work_item(metadata={})],
            ),
            _project(
                catalog_key=KEY_B,
                name="Beta",
                local_path="C:\\Projects\\Beta",
                tech_stack=["Rust"],
                work_items=[],
            ),
        ]
    )
    assert import_catalog(first, dry_run=True) == {"projects": 2, "work_items": 1}
    counts = import_catalog(first)
    assert counts == {"projects": 2, "work_items": 1}
    alpha = repo.get_project_by_catalog_key(db, KEY_A)
    assert alpha is not None
    assert alpha.monitored == 0
    assert alpha.source == "catalog"
    assert alpha.catalog_status == "active"
    assert len(repo.list_work_items_for_project(db, alpha.id)) == 1
    latest = repo.get_latest_catalog_import(db)
    assert latest is not None
    assert latest.project_count == 2
    assert latest.work_item_count == 1

    assert import_catalog(first) == {"projects": 2, "work_items": 1}
    assert repo.count_all_work_items(db) == 1


def test_import_catalog_rolls_back_on_failure(db, app_settings, monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(repo, "upsert_catalog_project", explode)
    with pytest.raises(RuntimeError, match="database exploded"):
        import_catalog(_catalog())
    assert repo.count_all_work_items(db) == 0


def test_main_validates_and_imports(tmp_path, db, app_settings, capsys) -> None:
    valid = _write(tmp_path, _catalog())
    assert main(["--catalog", str(valid), "--dry-run"]) == 0
    assert "validated 1 projects and 1 work items" in capsys.readouterr().out

    assert main(["--catalog", str(valid)]) == 0
    assert "imported 1 projects and 1 work items" in capsys.readouterr().out
    assert repo.get_project_by_catalog_key(db, KEY_A) is not None

    invalid = _write(tmp_path, {"schema_version": 1}, name="invalid.json")
    assert main(["--catalog", str(invalid)]) == 2
    assert "error:" in capsys.readouterr().err
