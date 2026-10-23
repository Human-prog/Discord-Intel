#!/usr/bin/env python3
"""Build a portable catalog of every project under a workstation directory.

Run this on the machine that owns the projects (for example Windows), then
import the resulting JSON on the DPI server with ``scripts/import_catalog.py``.
The scanner is read-only and uses only the Python standard library.

What it records per project:
  * stable catalog key and resolved local path
  * name, description, repository URL, tech stack, category/priority
  * Git branch, HEAD, dirty state, and recent commits as work items
  * last activity and a derived active/idle/dormant status

It never reads file contents beyond a bounded README/manifest prefix, never
follows junctions outside the scan root, and never includes credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCHEMA_VERSION = 1
DEFAULT_MAX_COMMITS = 25
MAX_README_BYTES = 24_000
MAX_DESCRIPTION_CHARS = 500
MAX_PROJECTS = 500

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "node_modules",
        "bower_components",
        "dist",
        "build",
        "target",
        "out",
        "bin",
        "obj",
        "coverage",
        "htmlcov",
        ".next",
        ".nuxt",
        ".turbo",
        ".cache",
        ".idea",
        ".vscode",
        ".vs",
        "vendor",
        "Pods",
        "DerivedData",
        "site-packages",
        ".gradle",
        ".m2",
        ".terraform",
    }
)

# These are generated/provider-output folders inside the Impeccable repository
# that happens to be the scan root.  They are not separate projects.
ROOT_INTERNAL_DIRS = frozenset(
    {
        ".agents",
        ".cargo",
        ".claude",
        ".claude-plugin",
        ".codex",
        ".cursor",
        ".cursor-plugin",
        ".dsh",
        ".gemini",
        ".github",
        ".grok",
        ".hermes",
        ".impeccable",
        ".kiro",
        ".omp",
        ".opencode",
        ".pi",
        ".qoder",
        ".rovodev",
        ".trae",
        ".trae-cn",
        ".veto",
        ".vibe",
        "browser-bundle",
        "cli",
        "crates",
        "demos",
        "docs",
        "extension",
        "plugin",
        "scripts",
        "site",
        "skill",
        "skills",
        "tests",
        "ui",
        "ui-ux-pro-max-skill",
        "vscode",
    }
)

MANIFEST_FILES = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "mix.exs",
    "pubspec.yaml",
    "requirements.txt",
    "setup.py",
    "environment.yml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "flake.nix",
    "index.html",
)
MANIFEST_GLOBS = ("*.sln", "*.csproj", "*.fsproj", "*.xcodeproj", "*.xcworkspace")

CATEGORY_RE = re.compile(r"^(\d{2})\s*-\s*(.+)$")
PRIORITY_BY_PREFIX = {
    "01": "high",
    "02": "medium",
    "03": "low",
    "04": "agent",
    "05": "idea",
}

TECH_BY_MARKER = {
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "setup.py": "Python",
    "environment.yml": "Python",
    "package.json": "Node.js",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java",
    "build.gradle": "Java/Kotlin",
    "build.gradle.kts": "Kotlin",
    "composer.json": "PHP",
    "Gemfile": "Ruby",
    "mix.exs": "Elixir",
    "pubspec.yaml": "Dart/Flutter",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker",
    "docker-compose.yaml": "Docker",
    "flake.nix": "Nix",
}

FRAMEWORK_HINTS = {
    "react": "React",
    "next": "Next.js",
    "vue": "Vue",
    "svelte": "Svelte",
    "astro": "Astro",
    "express": "Express",
    "fastify": "Fastify",
    "nestjs": "NestJS",
    "electron": "Electron",
    "discord.js": "discord.js",
    "discord.py": "discord.py",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy",
    "pytest": "pytest",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "transformers": "Transformers",
    "streamlit": "Streamlit",
    "playwright": "Playwright",
    "tailwindcss": "Tailwind CSS",
}


@dataclass
class Candidate:
    path: Path
    real_path: Path
    markers: list[str]
    category: str | None = None
    priority: str | None = None


@dataclass
class ProjectRecord:
    catalog_key: str
    name: str
    local_path: str
    relative_path: str
    description: str
    repo_url: str | None
    tech_stack: list[str]
    category: str | None
    priority: str | None
    catalog_status: str
    last_activity_utc: str | None
    markers: list[str]
    metadata: dict[str, object] = field(default_factory=dict)
    work_items: list[dict[str, object]] = field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _run_git(path: Path, args: list[str], timeout: int = 15) -> str | None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(  # noqa: S603 - fixed git executable, bounded arguments
            ["git", "-C", str(path), *args],  # noqa: S607 - resolved from PATH by design
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _sanitize_repo_url(value: str) -> str | None:
    url = value.strip()
    if not url:
        return None
    # git@github.com:owner/repo.git -> https://github.com/owner/repo
    if url.startswith("git@") and ":" in url:
        host, _, path = url[4:].partition(":")
        url = f"https://{host}/{path}"
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    host = parts.hostname or ""
    if not host:
        return None
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    cleaned = urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
    return cleaned.rstrip("/")


def _detect_markers(path: Path) -> list[str]:
    markers: list[str] = []
    if (path / ".git").exists():
        markers.append(".git")
    for name in MANIFEST_FILES:
        if (path / name).is_file():
            markers.append(name)
    for pattern in MANIFEST_GLOBS:
        try:
            if any(path.glob(pattern)):
                markers.append(pattern)
        except OSError:
            pass
    if not markers:
        # A README plus several source-like subdirectories is enough to treat
        # a directory as a project when it has no manifest.  Empty folders and
        # bare documentation folders stay out of the catalog.
        has_readme = any(
            (path / name).is_file()
            for name in ("README", "README.md", "README.rst", "README.txt", "readme.md")
        )
        if has_readme:
            try:
                subdirs = [
                    child
                    for child in path.iterdir()
                    if child.is_dir() and child.name not in IGNORED_DIRS
                ]
                source_files = [
                    child
                    for child in path.iterdir()
                    if child.is_file()
                    and child.suffix.lower()
                    in {
                        ".py",
                        ".js",
                        ".ts",
                        ".tsx",
                        ".jsx",
                        ".go",
                        ".rs",
                        ".java",
                        ".cs",
                        ".swift",
                        ".kt",
                    }
                ]
            except OSError:
                subdirs = []
                source_files = []
            if len(subdirs) >= 3 or source_files:
                markers.append("README")
    return markers


def _read_prefix(path: Path, limit: int = MAX_README_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _manifest_info(path: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    package = path / "package.json"
    if package.is_file():
        try:
            data = json.loads(_read_prefix(package, 200_000) or "{}")
        except (ValueError, TypeError):
            data = {}
        if isinstance(data, dict):
            for key in ("name", "version", "description"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    info[f"package_{key}"] = value.strip()
    pyproject = path / "pyproject.toml"
    if pyproject.is_file():
        text = _read_prefix(pyproject, 60_000)
        for key in ("name", "version", "description"):
            match = re.search(rf'(?m)^\s*{key}\s*=\s*["\']([^"\']+)["\']', text)
            if match:
                info[f"pyproject_{key}"] = match.group(1).strip()
    cargo = path / "Cargo.toml"
    if cargo.is_file():
        text = _read_prefix(cargo, 60_000)
        section = re.search(r"(?ms)^\[package\](.*?)(?:^\[|\Z)", text)
        if section:
            for key in ("name", "version", "description"):
                match = re.search(rf'(?m)^\s*{key}\s*=\s*["\']([^"\']+)["\']', section.group(1))
                if match:
                    info[f"cargo_{key}"] = match.group(1).strip()
    return info


def _readme_description(path: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "readme.md", "README"):
        readme = path / name
        if not readme.is_file():
            continue
        text = _read_prefix(readme)
        if not text:
            continue
        paragraphs: list[str] = []
        current: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            if line.startswith(("#", "![", "[![", "<img", "<p", "<div", "---", "===", "```")):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            if line.startswith(("<", "|")):
                continue
            line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
            line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
            line = re.sub(r"<[^>]+>", "", line)
            line = re.sub(r"[*_`>#]+", "", line).strip()
            if line:
                current.append(line)
        if current:
            paragraphs.append(" ".join(current))
        for paragraph in paragraphs:
            joined = " ".join(paragraph.split())
            if len(joined) >= 20:
                return joined[:MAX_DESCRIPTION_CHARS]
        if paragraphs:
            return paragraphs[0][:MAX_DESCRIPTION_CHARS]
    return ""


def _description(path: Path, manifest: dict[str, str]) -> str:
    for key in ("package_description", "pyproject_description", "cargo_description"):
        value = manifest.get(key, "").strip()
        if value:
            return value[:MAX_DESCRIPTION_CHARS]
    return _readme_description(path)


def _tech_stack(path: Path, markers: list[str], manifest: dict[str, str]) -> list[str]:
    stack: list[str] = []
    for marker in markers:
        tech = TECH_BY_MARKER.get(marker)
        if tech and tech not in stack:
            stack.append(tech)

    package = path / "package.json"
    if package.is_file():
        try:
            data = json.loads(_read_prefix(package, 200_000) or "{}")
        except (ValueError, TypeError):
            data = {}
        if isinstance(data, dict):
            deps: list[str] = []
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                value = data.get(key)
                if isinstance(value, dict):
                    deps.extend(str(name) for name in value)
            for dep in deps:
                hint = FRAMEWORK_HINTS.get(dep.lower())
                if hint and hint not in stack:
                    stack.append(hint)

    pyproject = path / "pyproject.toml"
    if pyproject.is_file():
        lowered = _read_prefix(pyproject, 60_000).lower()
        for dependency, hint in FRAMEWORK_HINTS.items():
            if dependency.lower() in lowered and hint not in stack:
                stack.append(hint)
    requirements = path / "requirements.txt"
    if requirements.is_file():
        lowered = _read_prefix(requirements, 60_000).lower()
        for dependency, hint in FRAMEWORK_HINTS.items():
            if dependency.lower() in lowered and hint not in stack:
                stack.append(hint)
    return stack[:10]


def _latest_mtime(path: Path, max_files: int = 4000) -> datetime | None:
    latest: float | None = None
    seen = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        for name in files:
            seen += 1
            if seen > max_files:
                break
            try:
                mtime = (Path(root) / name).stat().st_mtime
            except OSError:
                continue
            latest = mtime if latest is None else max(latest, mtime)
        if seen > max_files:
            break
    if latest is None:
        return None
    return datetime.fromtimestamp(latest, UTC)


def _parse_git_date(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _status_for(last_activity: datetime | None) -> str:
    if last_activity is None:
        return "unknown"
    age = _utc_now() - last_activity
    if age <= timedelta(days=30):
        return "active"
    if age <= timedelta(days=180):
        return "idle"
    return "dormant"


def _git_info(
    path: Path, max_commits: int
) -> tuple[dict[str, object], list[dict[str, object]], datetime | None]:
    inside = _run_git(path, ["rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        return {}, [], None
    branch = _run_git(path, ["branch", "--show-current"]) or ""
    head = _run_git(path, ["rev-parse", "HEAD"]) or ""
    remote = _run_git(path, ["remote", "get-url", "origin"])
    dirty_output = _run_git(path, ["status", "--porcelain"])
    dirty = bool(dirty_output)

    last_line = _run_git(path, ["log", "-1", "--format=%H%x1f%cI%x1f%an%x1f%s"])
    last_activity: datetime | None = None
    if last_line:
        parts = last_line.split("\x1f")
        if len(parts) >= 2:
            last_activity = _parse_git_date(parts[1])

    commits: list[dict[str, object]] = []
    log = _run_git(
        path,
        [
            "log",
            f"-n{max_commits}",
            "--format=%H%x1f%cI%x1f%an%x1f%s",
        ],
    )
    if log:
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 4:
                continue
            commit_hash, date_text, author, subject = parts[0], parts[1], parts[2], parts[3]
            occurred = _parse_git_date(date_text)
            commits.append(
                {
                    "external_id": commit_hash,
                    "work_type": "commit",
                    "title": subject[:500] or "(no commit subject)",
                    "body": f"{author} · {date_text}",
                    "status": "done",
                    "source": "git",
                    "occurred_at_utc": _iso(occurred) if occurred else date_text,
                    "metadata": {
                        "author": author,
                        "branch": branch,
                        "commit": commit_hash,
                    },
                }
            )

    info: dict[str, object] = {
        "branch": branch,
        "head": head,
        "dirty": dirty,
        "remote": _sanitize_repo_url(remote or ""),
        "commit_count_returned": len(commits),
    }
    return info, commits, last_activity


def _name_for(path: Path, manifest: dict[str, str]) -> str:
    for key in ("package_name", "pyproject_name", "cargo_name"):
        value = manifest.get(key, "").strip()
        if value and value.lower() not in {"app", "application", "package", "project"}:
            return value.lstrip("@").replace("/", " / ")[:200]
    return path.name[:200]


def _collect_candidates(root: Path, max_depth: int) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}
    root = root.resolve()

    def add(path: Path, markers: list[str]) -> None:
        try:
            real = Path(os.path.realpath(path))
        except OSError:
            return
        if not real.is_relative_to(root):
            return
        key = os.path.normcase(str(real))
        category = None
        priority = None
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = Path()
        if relative.parts:
            match = CATEGORY_RE.match(relative.parts[0])
            if match:
                category = relative.parts[0]
                priority = PRIORITY_BY_PREFIX.get(match.group(1))
        existing = candidates.get(key)
        if existing is None:
            candidates[key] = Candidate(
                path=path,
                real_path=real,
                markers=markers,
                category=category,
                priority=priority,
            )
        else:
            for marker in markers:
                if marker not in existing.markers:
                    existing.markers.append(marker)
            if existing.category is None and category is not None:
                existing.category = category
            if existing.priority is None and priority is not None:
                existing.priority = priority

    root_markers = _detect_markers(root)
    if root_markers:
        add(root, root_markers)

    def walk(path: Path, depth: int) -> None:
        if len(candidates) >= MAX_PROJECTS or depth > max_depth:
            return
        try:
            children = sorted(path.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            return
        for child in children:
            if not child.is_dir():
                continue
            if child.name in IGNORED_DIRS:
                continue
            try:
                real_child = Path(os.path.realpath(child))
            except OSError:
                continue
            # Root-level generated/provider folders are part of the Impeccable
            # checkout, not separate projects.  A nested Git repository is the
            # exception: it is its own project even if its name is on the list.
            if (
                real_child.parent == root
                and real_child.name in ROOT_INTERNAL_DIRS
                and not (real_child / ".git").exists()
            ):
                continue
            markers = _detect_markers(child)
            if markers:
                add(child, markers)
                continue
            walk(child, depth + 1)

    walk(root, 0)
    return candidates


def build_catalog(root: Path, max_commits: int) -> dict[str, object]:
    root = root.resolve()
    candidates = _collect_candidates(root, max_depth=4)
    projects: list[ProjectRecord] = []

    for candidate in candidates.values():
        if len(projects) >= MAX_PROJECTS:
            break
        real = candidate.real_path
        try:
            relative = real.relative_to(root)
        except ValueError:
            relative = candidate.path.relative_to(root)
        manifest = _manifest_info(real)
        git_info, commits, git_last_activity = _git_info(real, max_commits)
        file_last_activity = _latest_mtime(real)
        last_activity = git_last_activity
        if file_last_activity is not None:
            last_activity = (
                file_last_activity
                if last_activity is None
                else max(last_activity, file_last_activity)
            )
        catalog_key = hashlib.sha256(os.path.normcase(str(real)).encode("utf-8")).hexdigest()
        record = ProjectRecord(
            catalog_key=catalog_key,
            name=_name_for(real, manifest),
            local_path=str(real),
            relative_path=relative.as_posix(),
            description=_description(real, manifest),
            repo_url=_sanitize_repo_url(str(git_info.get("remote") or "")) or None,
            tech_stack=_tech_stack(real, candidate.markers, manifest),
            category=candidate.category,
            priority=candidate.priority,
            catalog_status=_status_for(last_activity),
            last_activity_utc=_iso(last_activity) if last_activity else None,
            markers=sorted(candidate.markers),
            metadata={
                "manifest": manifest,
                "git": git_info,
                "has_git": bool(git_info),
            },
            work_items=commits,
        )
        projects.append(record)

    def sort_key(record: ProjectRecord) -> tuple[int, str, str]:
        priority_order = {"high": 0, "medium": 1, "low": 2, "agent": 3, "idea": 4}
        return (
            priority_order.get(record.priority or "", 9),
            record.name.lower(),
            record.local_path.lower(),
        )

    projects.sort(key=sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(_utc_now()),
        "root": str(root),
        "project_count": len(projects),
        "work_item_count": sum(len(project.work_items) for project in projects),
        "projects": [
            {
                "catalog_key": project.catalog_key,
                "name": project.name,
                "local_path": project.local_path,
                "relative_path": project.relative_path,
                "description": project.description,
                "repo_url": project.repo_url,
                "tech_stack": project.tech_stack,
                "category": project.category,
                "priority": project.priority,
                "catalog_status": project.catalog_status,
                "last_activity_utc": project.last_activity_utc,
                "markers": project.markers,
                "metadata": project.metadata,
                "work_items": project.work_items,
            }
            for project in projects
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Directory to scan (default: the parent of this repository)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("catalog.json"),
        help="JSON file to write (default: ./catalog.json)",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=DEFAULT_MAX_COMMITS,
        help=f"Recent commits per project (default: {DEFAULT_MAX_COMMITS})",
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"error: scan root is not a directory: {root}", file=sys.stderr)
        return 2
    if args.max_commits < 0 or args.max_commits > 200:
        print("error: --max-commits must be between 0 and 200", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"scanning {root}", file=sys.stderr)
    catalog = build_catalog(root, args.max_commits)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {catalog['project_count']} projects and "
        f"{catalog['work_item_count']} work items to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
