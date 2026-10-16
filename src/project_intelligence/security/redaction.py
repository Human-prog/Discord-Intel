"""Secret redaction helpers (Phase 2).

Used by diagnostics and, in later phases, by logging, audit output, and
error reporting. These helpers are defense in depth: code that handles
secrets must still never pass raw values into logs or user-visible output
in the first place.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "***REDACTED***"

# Substrings that mark a configuration key or mapping key as secret-bearing.
_SECRET_KEY_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "authorization",
    "cookie",
    "api_key",
    "private_key",
)

# Common credential shapes found in free text (log lines, exception messages).
_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-=]{8,}"),
        f"Bearer {REDACTED}",
    ),
    (
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
        REDACTED,
    ),
    (
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        REDACTED,
    ),
    (
        re.compile(r"(?i)\b(token|api[_-]?key|secret|password)\s*[:=]\s*[^\s,;'\"]+"),
        r"\1=" + REDACTED,
    ),
)


def is_secret_key(name: str) -> bool:
    """Return True when a key name suggests its value is secret-bearing."""
    lowered = name.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def redact_value(name: str, value: Any) -> Any:
    """Return the value unchanged, or the redaction marker for secret keys."""
    return REDACTED if is_secret_key(name) else value


def redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Redact secret-looking keys in a mapping (recursively for nested dicts)."""
    result: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            result[str(key)] = redact_mapping(value)
        else:
            result[str(key)] = redact_value(str(key), value)
    return result


def redact_text(text: str) -> str:
    """Redact common credential shapes from free text such as log messages."""
    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
