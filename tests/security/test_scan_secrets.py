"""Tests for the repository secret scanner.

Credential-shaped strings in this file are constructed at runtime (never
present as literals) so the repository itself stays scanner-clean; the final
test enforces exactly that property.
"""

from __future__ import annotations

from pathlib import Path

from project_intelligence.security.secret_scan import (
    MAX_FILE_BYTES,
    scan_file,
    scan_tree,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# A fake GitHub token built at runtime; see module docstring.
FAKE_GITHUB_TOKEN = "ghp_" + "a" * 30


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_clean_file_has_no_findings(tmp_path):
    path = _write(tmp_path, "clean.py", "API_KEY_NAME = 'not a secret'\nvalue = 42\n")
    assert scan_file(path) == []
    assert scan_tree(path) == []


def test_detects_github_pat(tmp_path):
    fake = "github_pat_" + "AbCd1234" * 6
    path = _write(tmp_path, "leak.txt", f"line one\ntoken: {fake}\n")
    findings = scan_file(path)
    assert any(f.rule == "github_pat" for f in findings)
    assert any(f.line_number == 2 for f in findings)


def test_detects_github_token_prefixes(tmp_path):
    for prefix in ("ghp", "gho", "ghu", "ghs", "ghr"):
        fake = prefix + "_" + "a1b2c3d4" * 4
        path = _write(tmp_path, f"{prefix}.txt", fake + "\n")
        assert any(f.rule == "github_token" for f in scan_file(path)), prefix


def test_detects_discord_token_shape(tmp_path):
    fake = "M" + "a" * 23 + "." + "b" * 6 + "." + "c" * 27
    path = _write(tmp_path, "config.ini", "bot = " + fake + "\n")
    assert any(f.rule == "discord_bot_token" for f in scan_file(path))


def test_detects_generic_assignment(tmp_path):
    fake = "a1B2" * 8
    path = _write(tmp_path, "settings.env", "api_key=" + fake + "\n")
    assert any(f.rule == "generic_assignment" for f in scan_file(path))


def test_detects_private_key_header(tmp_path):
    header = "-----BEGIN " + "RSA " + "PRIVATE KEY-----"
    path = _write(tmp_path, "key.pem", header + "\nMIIE-not-a-real-key\n")
    assert any(f.rule == "private_key_header" for f in scan_file(path))


def test_detects_aws_slack_openai_bearer(tmp_path):
    aws = "AKIA" + "F" * 16
    slack = "xoxb-" + "1234567890123"
    openai_style = "sk-" + "x" * 30
    bearer = "Bearer " + "A" * 40
    path = _write(tmp_path, "all.txt", "\n".join([aws, slack, openai_style, bearer]) + "\n")
    rules = {f.rule for f in scan_file(path)}
    assert {"aws_access_key", "slack_token", "openai_style_key", "bearer_header"} <= rules


def test_benign_config_lines_are_not_flagged(tmp_path):
    path = _write(
        tmp_path,
        "notes.md",
        "Discord IDs are numeric, e.g. 123456789012345678\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n"
        "OPENCODE_ENABLED=false\n",
    )
    assert scan_file(path) == []


def test_excluded_directories_are_pruned(tmp_path):
    leak = "github_pat_" + "Ab1" * 10
    for excluded in (".git", "__pycache__"):
        target = tmp_path / excluded
        target.mkdir()
        (target / "leak.txt").write_text(leak + "\n", encoding="utf-8")
    assert scan_tree(tmp_path) == []


def test_excluded_env_file_is_skipped_but_example_is_scanned(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("github_pat_" + "Ab1" * 10 + "\n", encoding="utf-8")
    assert scan_tree(env_file) == []

    example = tmp_path / ".env.example"
    example.write_text("DISCORD_BOT_TOKEN=\n", encoding="utf-8")
    assert scan_tree(tmp_path) == []

    example.write_text("github_pat_" + "Ab1" * 10 + "\n", encoding="utf-8")
    assert any(f.path.name == ".env.example" for f in scan_tree(tmp_path))


def test_binary_files_are_skipped(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"\x00\x01" + (FAKE_GITHUB_TOKEN).encode() + b"\x00")
    assert scan_file(blob) == []


def test_oversized_files_are_skipped(tmp_path):
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * (MAX_FILE_BYTES + 1))
    assert scan_file(big) == []


def test_missing_file_yields_no_findings(tmp_path):
    assert scan_file(tmp_path / "missing.txt") == []


def test_findings_never_include_matched_value(tmp_path):
    path = _write(tmp_path, "leak.txt", FAKE_GITHUB_TOKEN + "\n")
    findings = scan_file(path)
    assert findings
    for finding in findings:
        assert FAKE_GITHUB_TOKEN not in repr(finding)
        assert FAKE_GITHUB_TOKEN not in str(finding)


def test_scan_tree_reports_relative_paths_and_line_numbers(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "leak.txt").write_text("ok\n" + FAKE_GITHUB_TOKEN + "\n", encoding="utf-8")
    findings = scan_tree(tmp_path)
    assert len(findings) == 1
    assert findings[0].path == Path("sub") / "leak.txt"
    assert findings[0].line_number == 2


def test_repository_tree_is_clean():
    findings = scan_tree(REPO_ROOT)
    rendering = [f"{f.path}:{f.line_number}: {f.rule}" for f in findings]
    assert findings == [], f"repository contains credential-shaped strings: {rendering}"
