"""Unit tests for src/project_intelligence/security/redaction.py."""

from __future__ import annotations

from project_intelligence.security.redaction import (
    REDACTED,
    is_secret_key,
    redact_mapping,
    redact_text,
    redact_value,
)


def test_secret_key_detection():
    assert is_secret_key("DISCORD_BOT_TOKEN")
    assert is_secret_key("github_read_only_token")
    assert is_secret_key("dashboard_session_secret_file")
    assert is_secret_key("RESEARCH_API_KEY")
    assert not is_secret_key("GITHUB_APP_ID")
    assert not is_secret_key("APP_LOG_LEVEL")


def test_redact_value_masks_secret_keys_only():
    assert redact_value("DISCORD_BOT_TOKEN", "abc") == REDACTED
    assert redact_value("APP_ENV", "development") == "development"


def test_redact_mapping_flat():
    result = redact_mapping({"discord_bot_token": "abc", "app_env": "development"})
    assert result == {"discord_bot_token": REDACTED, "app_env": "development"}


def test_redact_mapping_nested():
    result = redact_mapping({"github": {"read_only_token": "abc", "mode": "token"}})
    assert result == {"github": {"read_only_token": REDACTED, "mode": "token"}}


def test_redact_text_bearer_header():
    text = "Authorization: Bearer abcdefghijklmnop.qrstuv-wxyz"
    assert "abcdefghijklmnop" not in redact_text(text)
    assert REDACTED in redact_text(text)


def test_redact_text_github_tokens():
    # Constructed programmatically so repository secret scans stay clean.
    ghp_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"
    pat_token = "github_pat_" + "AbCdEfGhIjKlMnOpQrStUvWx"
    text = f"token {ghp_token} and {pat_token}"
    redacted = redact_text(text)
    assert ghp_token not in redacted
    assert pat_token not in redacted


def test_redact_text_key_value_patterns():
    text = "token=abcd1234 secret: xyz9876 api_key=QWERTY123"
    redacted = redact_text(text)
    assert "abcd1234" not in redacted
    assert "xyz9876" not in redacted
    assert "QWERTY123" not in redacted
    assert redacted.count(REDACTED) == 3
