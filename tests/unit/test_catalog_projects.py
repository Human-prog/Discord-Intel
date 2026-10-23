"""Workstation project scanner for the portable DPI catalog."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts import catalog_projects as scanner
from scripts.catalog_projects import (
    Candidate,
    ProjectRecord,
    _collect_candidates,
    _description,
    _detect_markers,
    _git_info,
    _iso,
    _latest_mtime,
    _manifest_info,
    _name_for,
    _parse_git_date,
    _read_prefix,
    _readme_description,
    _run_git,
    _sanitize_repo_url,
    _status_for,
    _tech_stack,
    _utc_now,
    build_catalog,
    main,
)


def _git(path: Path, *args: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed git executable, test-owned arguments
        ["git", "-C", str(path), *args],  # noqa: S607 - test fixture relies on PATH git
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _make_repo(path: Path, *, remote: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "README.md").write_text(
        "# Demo\n\nA demo project with a long enough description for the scanner.\n",
        encoding="utf-8",
    )
    (path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(
        path,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test User",
        "commit",
        "-qm",
        "Initial commit",
    )
    if remote:
        _git(path, "remote", "add", "origin", remote)
    return path


def test_time_and_status_helpers() -> None:
    assert _iso(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00Z"
    assert _utc_now().tzinfo is UTC
    assert _status_for(None) == "unknown"
    assert _status_for(_utc_now() - timedelta(days=2)) == "active"
    assert _status_for(_utc_now() - timedelta(days=60)) == "idle"
    assert _status_for(_utc_now() - timedelta(days=200)) == "dormant"
    assert _parse_git_date("") is None
    assert _parse_git_date("2026-10-20T00:00:00Z") == datetime(2026, 10, 20, tzinfo=UTC)
    assert _parse_git_date("not-a-date") is None


def test_sanitize_repo_url() -> None:
    assert _sanitize_repo_url("") is None
    assert (
        _sanitize_repo_url("git@github.com:owner/repo.git") == "https://github.com/owner/repo.git"
    )
    assert _sanitize_repo_url("https://user:pass@example.com:8443/a/b.git/") == (
        "https://example.com:8443/a/b.git"
    )
    assert _sanitize_repo_url("http://example.com/repo?x=1#frag") == "http://example.com/repo?x=1"
    assert _sanitize_repo_url("ssh://example.com/repo") is None
    assert _sanitize_repo_url("https:///repo") is None


def test_readme_description_extracts_clean_paragraph(tmp_path) -> None:
    (tmp_path / "README.md").write_text(
        "# Title\n\n[![badge](https://img)]\n\n"
        "This is a *useful* [project](https://example.com) with `code` and <b>html</b>.\n"
        "Second line of the paragraph.\n\nAnother paragraph that is also long enough to count.\n",
        encoding="utf-8",
    )
    description = _readme_description(tmp_path)
    assert description.startswith("This is a useful project with code and html.")
    assert "Second line" in description

    (tmp_path / "README.md").write_text("# Title\n\nShort.\n", encoding="utf-8")
    assert _readme_description(tmp_path) == "Short."

    (tmp_path / "README.md").write_text("", encoding="utf-8")
    assert _readme_description(tmp_path) == ""
    assert _readme_description(tmp_path / "missing") == ""


def test_readme_description_skips_structural_lines(tmp_path) -> None:
    (tmp_path / "README.txt").write_text(
        "=== heading ===\n"
        "![image](x)\n"
        "<div>html</div>\n"
        "| table |\n"
        "```\n"
        "code\n"
        "```\n"
        "A real paragraph with enough length to be selected.\n",
        encoding="utf-8",
    )
    assert _readme_description(tmp_path).startswith("A real paragraph")


def test_manifest_info_and_description(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "@scope/pkg",
                "version": "1.2.3",
                "description": "Package description",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "py-name"\nversion = "0.1.0"\ndescription = "Py description"\n',
        encoding="utf-8",
    )
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "crate-name"\nversion = "2.0.0"\ndescription = "Cargo description"\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("README description that is long enough.", encoding="utf-8")
    manifest = _manifest_info(tmp_path)
    assert manifest["package_name"] == "@scope/pkg"
    assert manifest["pyproject_name"] == "py-name"
    assert manifest["cargo_name"] == "crate-name"
    assert _description(tmp_path, manifest) == "Package description"
    assert _name_for(tmp_path, manifest) == "scope / pkg"

    (tmp_path / "package.json").write_text("{bad", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("not toml", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("not toml", encoding="utf-8")
    assert _manifest_info(tmp_path) == {}
    assert _description(tmp_path, {}) == "README description that is long enough."
    assert _name_for(tmp_path, {}) == tmp_path.name

    (tmp_path / "package.json").write_text("[]", encoding="utf-8")
    assert _manifest_info(tmp_path) == {}


def test_name_for_rejects_generic_names(tmp_path) -> None:
    assert _name_for(tmp_path, {"package_name": "app"}) == tmp_path.name
    assert _name_for(tmp_path, {"package_name": "Project"}) == tmp_path.name
    assert _name_for(tmp_path, {"pyproject_name": "real-name"}) == "real-name"


def test_tech_stack_from_markers_and_manifests(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"react": "^1", "unknown": "1"},
                "devDependencies": {"next": "1"},
                "peerDependencies": {"svelte": "1"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = ['fastapi', 'pydantic', 'pytest']\n", encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text("django\nflask\n", encoding="utf-8")
    stack = _tech_stack(
        tmp_path,
        ["package.json", "pyproject.toml", "requirements.txt", "Cargo.toml"],
        {},
    )
    assert "Node.js" in stack
    assert "Rust" in stack
    assert "React" in stack
    assert "Next.js" in stack
    assert "Svelte" in stack
    assert "FastAPI" in stack
    assert "Pydantic" in stack
    assert "pytest" in stack
    assert "Django" in stack
    assert len(stack) <= 10


def test_tech_stack_handles_bad_package_json(tmp_path) -> None:
    (tmp_path / "package.json").write_text("{bad", encoding="utf-8")
    assert _tech_stack(tmp_path, ["package.json"], {}) == ["Node.js"]


def test_read_prefix_and_markers(tmp_path) -> None:
    assert _read_prefix(tmp_path / "missing") == ""
    (tmp_path / "README").write_text("hello", encoding="utf-8")
    assert _read_prefix(tmp_path / "README", limit=2) == "he"

    empty = tmp_path / "empty"
    empty.mkdir()
    assert _detect_markers(empty) == []

    manifest = tmp_path / "manifest"
    manifest.mkdir()
    (manifest / ".git").mkdir()
    (manifest / "package.json").write_text("{}", encoding="utf-8")
    (manifest / "project.sln").write_text("", encoding="utf-8")
    assert _detect_markers(manifest) == [".git", "package.json", "*.sln"]

    readme_source = tmp_path / "readme-source"
    readme_source.mkdir()
    (readme_source / "README.md").write_text("x", encoding="utf-8")
    (readme_source / "main.py").write_text("x", encoding="utf-8")
    assert _detect_markers(readme_source) == ["README"]

    readme_dirs = tmp_path / "readme-dirs"
    readme_dirs.mkdir()
    (readme_dirs / "README").write_text("x", encoding="utf-8")
    for name in ("a", "b", "c"):
        (readme_dirs / name).mkdir()
    assert _detect_markers(readme_dirs) == ["README"]

    one_dir = tmp_path / "one-dir"
    one_dir.mkdir()
    (one_dir / "README").write_text("x", encoding="utf-8")
    (one_dir / "only").mkdir()
    assert _detect_markers(one_dir) == []


def test_latest_mtime(tmp_path) -> None:
    assert _latest_mtime(tmp_path) is None
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    latest = _latest_mtime(tmp_path)
    assert latest is not None
    assert latest.tzinfo is UTC
    assert _latest_mtime(tmp_path, max_files=1) is not None

    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / ".git").mkdir()
    (ignored / ".git" / "config").write_text("x", encoding="utf-8")
    assert _latest_mtime(ignored) is None


def test_run_git_and_git_info(tmp_path, monkeypatch) -> None:
    assert _run_git(tmp_path, ["status"]) is None or _run_git(tmp_path, ["status"]) == ""
    repo = _make_repo(tmp_path / "repo", remote="git@github.com:owner/repo.git")
    info, commits, last = _git_info(repo, 5)
    assert info["branch"]
    assert info["head"]
    assert info["remote"] == "https://github.com/owner/repo.git"
    assert info["commit_count_returned"] == 1
    assert commits[0]["title"] == "Initial commit"
    assert commits[0]["external_id"] == info["head"]
    assert last is not None

    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    info, _, _ = _git_info(repo, 0)
    assert info["dirty"] is True
    assert info["commit_count_returned"] == 0

    no_git = tmp_path / "plain"
    no_git.mkdir()
    assert _git_info(no_git, 5) == ({}, [], None)

    def explode(*args, **kwargs):
        raise OSError("git missing")

    monkeypatch.setattr(scanner.subprocess, "run", explode)
    assert _run_git(repo, ["status"]) is None


def test_run_git_nonzero_and_empty_repo(tmp_path) -> None:
    assert _run_git(tmp_path, ["not-a-real-command"]) is None
    empty = tmp_path / "empty-repo"
    empty.mkdir()
    _git(empty, "init", "-q")
    info, commits, last = _git_info(empty, 5)
    assert info["branch"]
    assert info["head"] == ""
    assert commits == []
    assert last is None


def test_collect_candidates_and_category(tmp_path) -> None:
    high = tmp_path / "01 - High Priority Projects" / "Alpha"
    high.mkdir(parents=True)
    (high / "pyproject.toml").write_text('[project]\nname = "alpha"\n', encoding="utf-8")
    medium = tmp_path / "02 - Medium Priority" / "Beta"
    medium.mkdir(parents=True)
    (medium / "package.json").write_text("{}", encoding="utf-8")
    idea = tmp_path / "05 - Ideas" / "Gamma"
    idea.mkdir(parents=True)
    (idea / "README.md").write_text("x", encoding="utf-8")
    (idea / "main.py").write_text("x", encoding="utf-8")
    internal = tmp_path / "demos" / "Ignored"
    internal.mkdir(parents=True)
    (internal / "package.json").write_text("{}", encoding="utf-8")
    ignored = tmp_path / "node_modules" / "Ignored"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}", encoding="utf-8")

    candidates = _collect_candidates(tmp_path, max_depth=4)
    names = {candidate.path.name for candidate in candidates.values()}
    assert names == {"Alpha", "Beta", "Gamma"}
    by_name = {candidate.path.name: candidate for candidate in candidates.values()}
    assert by_name["Alpha"].category == "01 - High Priority Projects"
    assert by_name["Alpha"].priority == "high"
    assert by_name["Beta"].priority == "medium"
    assert by_name["Gamma"].priority == "idea"

    # A root-internal folder that is itself a Git repository is a project.
    _make_repo(tmp_path / "demos")
    nested_candidates = _collect_candidates(tmp_path, max_depth=4)
    assert any(candidate.path.name == "demos" for candidate in nested_candidates.values())

    # Max depth keeps deeper projects out.
    deep = tmp_path / "a" / "b" / "c" / "d" / "Deep"
    deep.mkdir(parents=True)
    (deep / "package.json").write_text("{}", encoding="utf-8")
    shallow = _collect_candidates(tmp_path, max_depth=1)
    assert "Deep" not in {candidate.path.name for candidate in shallow.values()}


def test_collect_candidates_root_and_max_projects(tmp_path, monkeypatch) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    candidates = _collect_candidates(tmp_path, max_depth=2)
    assert any(candidate.path == tmp_path.resolve() for candidate in candidates.values())

    first = tmp_path / "one"
    first.mkdir()
    (first / "package.json").write_text("{}", encoding="utf-8")
    second = tmp_path / "two"
    second.mkdir()
    (second / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(scanner, "MAX_PROJECTS", 1)
    limited = _collect_candidates(tmp_path, max_depth=2)
    assert len(limited) == 1


def test_build_catalog(tmp_path) -> None:
    repo = _make_repo(tmp_path / "Alpha")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "alpha-project"\ndescription = "A test project"\n', encoding="utf-8"
    )
    (repo / "README.md").write_text(
        "A longer README description for the project.\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test User",
        "commit",
        "-qm",
        "Second commit",
    )
    catalog = build_catalog(tmp_path, max_commits=10)
    assert catalog["schema_version"] == 1
    assert catalog["project_count"] == 1
    assert catalog["work_item_count"] >= 1
    project = catalog["projects"][0]
    assert project["name"] == "alpha-project"
    assert project["description"] == "A test project"
    assert project["repo_url"] is None
    assert project["category"] is None
    assert project["markers"]
    assert project["metadata"]["has_git"] is True
    assert project["catalog_key"]
    assert project["relative_path"] == "Alpha"

    # A project without Git still gets file-based activity and status.
    plain = tmp_path / "Plain"
    plain.mkdir()
    (plain / "README.md").write_text(
        "A plain project description with enough text.\n", encoding="utf-8"
    )
    (plain / "main.py").write_text("print('plain')\n", encoding="utf-8")
    catalog = build_catalog(tmp_path, max_commits=0)
    names = {project["name"] for project in catalog["projects"]}
    assert "Alpha" in names or "alpha-project" in names
    assert "Plain" in names


def test_build_catalog_limits_projects(tmp_path, monkeypatch) -> None:
    for name in ("a", "b"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(scanner, "MAX_PROJECTS", 1)
    catalog = build_catalog(tmp_path, max_commits=0)
    assert catalog["project_count"] == 1


def test_main_errors_and_success(tmp_path, capsys) -> None:
    assert main(["--root", str(tmp_path / "missing")]) == 2
    assert main(["--root", str(tmp_path), "--max-commits", "-1"]) == 2
    assert main(["--root", str(tmp_path), "--max-commits", "201"]) == 2

    project = tmp_path / "Project"
    project.mkdir()
    (project / "package.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "out" / "catalog.json"
    assert main(["--root", str(tmp_path), "--output", str(output), "--verbose"]) == 0
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["project_count"] == 1
    captured = capsys.readouterr()
    assert "scanning" in captured.err
    assert "wrote 1 projects" in captured.out


def test_candidate_and_record_dataclasses() -> None:
    candidate = Candidate(path=Path("a"), real_path=Path("a"), markers=["x"])
    assert candidate.category is None
    record = ProjectRecord(
        catalog_key="k",
        name="n",
        local_path="p",
        relative_path="r",
        description="d",
        repo_url=None,
        tech_stack=[],
        category=None,
        priority=None,
        catalog_status="unknown",
        last_activity_utc=None,
        markers=[],
    )
    assert record.metadata == {}
    assert record.work_items == []
