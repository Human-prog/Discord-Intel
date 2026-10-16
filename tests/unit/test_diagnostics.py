"""Unit tests for src/project_intelligence/diagnostics.py.

The core security property under test: diagnostics never contain secret
values, only "set"/"unset" status markers.
"""

from __future__ import annotations

import shutil

from project_intelligence.diagnostics import (
    check_runtime_prerequisites,
    format_summary,
    summarize_settings,
)

DISCORD_SECRET = "DISCORDTOKENVALUE1234567890abcd"
GITHUB_SECRET = "GITHUBTOKENVALUE1234567890abcd"
RESEARCH_SECRET = "RESEARCHKEYVALUE1234567890abcd"


def _settings_with_secrets(make_settings):
    return make_settings(
        discord_bot_token=DISCORD_SECRET,
        discord_owner_user_ids=[123],
        github_mode="token",
        github_read_only_token=GITHUB_SECRET,
        research_provider="tavily",
        research_api_key=RESEARCH_SECRET,
    )


def test_summary_never_contains_secret_values(make_settings):
    settings = _settings_with_secrets(make_settings)
    summary = summarize_settings(settings)
    text = format_summary(summary)

    for secret in (DISCORD_SECRET, GITHUB_SECRET, RESEARCH_SECRET):
        assert secret not in text, "secret value leaked into diagnostics output"


def test_summary_reports_set_and_unset_statuses(make_settings):
    summary = summarize_settings(_settings_with_secrets(make_settings))
    assert summary["discord"]["bot_token"] == "set"
    assert summary["github"]["read_only_token"] == "set"
    assert summary["research"]["api_key"] == "set"
    assert summary["discord"]["owner_user_ids"] == 1

    default_summary = summarize_settings(make_settings())
    assert default_summary["discord"]["bot_token"] == "unset"
    assert default_summary["github"]["read_only_token"] == "unset"
    assert default_summary["research"]["api_key"] == "unset"
    assert default_summary["research"]["provider"] == "disabled"
    assert default_summary["opencode"]["enabled"] is False


def test_runtime_prereq_missing_github_key_file(make_settings, tmp_path):
    settings = make_settings(
        github_mode="app",
        github_app_id=1,
        github_app_private_key_file=str(tmp_path / "missing.pem"),
    )
    errors = [m for level, m in check_runtime_prerequisites(settings) if level == "error"]
    assert any("not found" in message for message in errors)


def test_runtime_prereq_existing_github_key_file_is_ok(make_settings, tmp_path):
    key_file = tmp_path / "key.pem"
    key_file.write_text("test fixture only, not a real key", encoding="utf-8")
    settings = make_settings(
        github_mode="app",
        github_app_id=1,
        github_app_private_key_file=str(key_file),
    )
    errors = [m for level, m in check_runtime_prerequisites(settings) if level == "error"]
    assert errors == []


def test_runtime_prereq_opencode_command_checked(make_settings, tmp_path, monkeypatch):
    settings = make_settings(
        opencode_enabled=True,
        opencode_command="opencode",
        opencode_allowed_worktrees=[str(tmp_path)],
    )

    monkeypatch.setattr(shutil, "which", lambda name: None)
    errors = [m for level, m in check_runtime_prerequisites(settings) if level == "error"]
    assert any("OpenCode command not found" in message for message in errors)

    monkeypatch.setattr(shutil, "which", lambda name: "C:/fake/opencode")
    errors = [m for level, m in check_runtime_prerequisites(settings) if level == "error"]
    assert errors == []


def test_runtime_prereq_missing_data_dir_is_info_not_error(make_settings, tmp_path):
    settings = make_settings(data_dir=str(tmp_path / "does-not-exist"))
    checks = check_runtime_prerequisites(settings)
    assert any(level == "info" for level, _ in checks)
    assert not any(level == "error" for level, _ in checks)
