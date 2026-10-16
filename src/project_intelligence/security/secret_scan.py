"""Repository secret scanner.

Deterministic, offline scanner for credential-shaped strings. Used locally
before commits and in CI on every push. It reports the file, line number, and
rule name only - never the matched value - so logs cannot leak a secret.

Test fixtures that need credential-shaped strings must build them
programmatically (for example ``"ghp_" + "a" * 30``) so this repository's own
tree stays scanner-clean; the scanner tests enforce that property.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Directories never scanned: VCS internals, virtualenvs, caches, and build
# output. Path parts are compared by name at every depth.
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".eggs",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "__pycache__",
    }
)

# Files never scanned. A local .env is expected to hold real secrets by
# design and is git-ignored; what must stay clean is everything committed.
EXCLUDED_FILES = frozenset({".env"})

# Files larger than this are skipped (checked before reading) to keep scans
# fast and bounded; configuration and source files are far below this size.
MAX_FILE_BYTES = 20 * 1024 * 1024

# Matched values are never returned or logged; only the rule name is.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    (
        "discord_bot_token",
        re.compile(r"\b[MNO][A-Za-z0-9]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b"),
    ),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    (
        "bearer_header",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{30,}\b"),
    ),
    (
        "generic_assignment",
        re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[A-Za-z0-9_\-]{24,}\b"),
    ),
)


@dataclass(frozen=True)
class Finding:
    """One rule match. Deliberately carries no matched text."""

    path: Path
    line_number: int
    rule: str


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def iter_files(root: Path) -> Iterator[Path]:
    """Yield candidate files under ``root`` in deterministic order.

    Excluded directories are pruned during traversal; ``root`` itself may be
    a single file.
    """
    root = Path(root)
    if root.is_file():
        if root.name not in EXCLUDED_FILES:
            yield root
        return

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for filename in sorted(filenames):
            if filename in EXCLUDED_FILES:
                continue
            yield Path(dirpath) / filename


def scan_file(path: Path, *, display_path: Path | None = None) -> list[Finding]:
    """Scan a single file. ``display_path`` overrides the path in findings."""
    path = Path(path)
    shown = path if display_path is None else display_path
    findings: list[Finding] = []

    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return findings
        data = path.read_bytes()
    except OSError:
        return findings

    if _is_binary(data):
        return findings

    text = data.decode("utf-8", errors="replace")
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in _PATTERNS:
            if pattern.search(line):
                findings.append(Finding(path=shown, line_number=line_number, rule=rule))
    return findings


def scan_tree(root: Path) -> list[Finding]:
    """Scan a directory (or single file) and return findings in stable order.

    Findings under a directory use paths relative to ``root`` for readable
    output.
    """
    root = Path(root)
    findings: list[Finding] = []
    single_file = root.is_file()
    for path in iter_files(root):
        shown = path if single_file else path.relative_to(root)
        findings.extend(scan_file(path, display_path=shown))
    return findings
