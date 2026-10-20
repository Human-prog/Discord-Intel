"""Secret and sensitive-data redaction tests (Phase 5)."""

from __future__ import annotations

import re

import pytest

from project_intelligence.security import redaction
from project_intelligence.security.redaction import (
    REDACTED,
    _redact_value_structural,
    is_secret_key,
    redact_mapping,
    redact_text,
    redact_value,
)

# ---------------------------------------------------------------------------
# Text rules
# ---------------------------------------------------------------------------


def test_discord_bot_token_is_redacted() -> None:
    assert redact_text("Bot " + "A" * 24) == "[REDACTED: discord bot token]"


def test_github_pat_is_redacted() -> None:
    assert redact_text("ghp_" + "a" * 36) == "[REDACTED: github PAT]"
    assert redact_text("github_pat_" + "b" * 20) == "[REDACTED: github PAT]"


def test_token_assignment_is_redacted() -> None:
    assert redact_text("token=supersecret") == REDACTED
    assert redact_text("API_KEY=abc123") == REDACTED
    assert redact_text("password = hunter2") == REDACTED


def test_bearer_header_keeps_only_the_label() -> None:
    text = "Authorization: Bearer abc.def-123_~+/"
    assert redact_text(text) == "Authorization: Bearer [REDACTED]"


def test_interaction_json_is_redacted() -> None:
    assert redact_text('{"token": "abc123", "user": 1}') == "[REDACTED: interaction JSON]"


def test_urls_are_redacted() -> None:
    """Over-redaction is intentional: URLs may carry credentials."""
    assert redact_text("see https://example.com/path") == "see [REDACTED: url in token field]"


def test_openai_key_is_redacted() -> None:
    assert redact_text("sk-" + "a" * 48) == "[REDACTED: openai key]"


def test_cloud_key_assignment_keeps_service_name() -> None:
    assert redact_text('aws_key="abcdefghijklmnop"') == "aws_key=[REDACTED]"
    assert redact_text('anthropic_key="abcdefghijklmnopq"') == "anthropic_key=[REDACTED]"


def test_private_ip_is_redacted() -> None:
    assert redact_text("host 192.168.1.10 is up") == "host [REDACTED: private IP] is up"
    assert redact_text("10.0.0.5") == "[REDACTED: private IP]"


def test_colon_separated_secret_is_redacted() -> None:
    assert redact_text("secret: hunter2") == REDACTED
    assert redact_text("api_key: abc") == REDACTED


def test_benign_text_is_untouched() -> None:
    assert redact_text("deploy finished in 42 seconds") == "deploy finished in 42 seconds"


def test_non_strings_are_stringified() -> None:
    assert redact_text(42) == "42"
    assert redact_text(False) == "False"


def test_unprintable_objects_are_redacted() -> None:
    class Unprintable:
        def __str__(self) -> str:
            raise RuntimeError("no printable form")

    assert redact_text(Unprintable()) == REDACTED


def test_broken_rule_never_leaks_or_raises(monkeypatch) -> None:
    def _boom(match: re.Match[str]) -> str:
        raise RuntimeError("broken replacement")

    monkeypatch.setattr(redaction, "REDACRULES", [(re.compile("secret"), _boom)])
    assert redact_text("secret") == "secret"


# ---------------------------------------------------------------------------
# Key-based redaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "discord_bot_token",
        "github_read_only_token",
        "dashboard_session_secret_file",
        "research_api_key",
        "read_only_token",
        "DISCORD_BOT_TOKEN",
    ],
)
def test_secret_keys_are_detected(key: str) -> None:
    assert is_secret_key(key) is True


@pytest.mark.parametrize("key", ["name", "allowed_root", "token_count", ""])
def test_non_secret_keys_are_ignored(key: str) -> None:
    assert is_secret_key(key) is False


def test_redact_value_only_masks_secret_keys() -> None:
    assert redact_value("DISCORD_BOT_TOKEN", "abc") == REDACTED
    assert redact_value("name", "abc") == "abc"


def test_redact_mapping_recurses() -> None:
    data = {
        "discord_bot_token": "abc",
        "nested": {"research_api_key": "def", "keep": 1},
        "items": [{"github_read_only_token": "ghi"}, "plain"],
        "other": "token=abc",
    }
    result = redact_mapping(data)

    assert result["discord_bot_token"] == REDACTED
    assert result["nested"] == {"research_api_key": REDACTED, "keep": 1}
    assert result["items"] == [{"github_read_only_token": REDACTED}, "plain"]
    # Non-secret keys keep their (unexamined) values.
    assert result["other"] == "token=abc"


def test_structural_redaction_handles_every_container() -> None:
    value = {
        "text": "token=abc",
        "nested": {"url": "https://example.com"},
        "list": ["secret: x", 7],
        "tuple": ("ghp_" + "a" * 36, 8),
        "number": 9,
    }
    result = _redact_value_structural(value)

    assert result["text"] == REDACTED
    assert result["nested"] == {"url": "[REDACTED: url in token field]"}
    assert result["list"] == [REDACTED, 7]
    assert result["tuple"] == ("[REDACTED: github PAT]", 8)
    assert result["number"] == 9
