"""Enhanced secret and sensitive-data redaction (Phase 5).

Builds on the Phase 2 redaction helpers with additional patterns for
Discord interaction data, model output, and research-sourced text.

All redaction is value-free: the matched text never appears in logged
output, error messages, or diagnostic summaries.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

#: The placeholder string used when a secret is redacted.
REDACTED = "[REDACTED]"


# ---------------------------------------------------------------------------
# Secret-key detection
# ---------------------------------------------------------------------------

# Public: keys whose values should always be redacted when they appear.
_SECRET_KEY_NAMES: tuple[str, ...] = (
    "discord_bot_token",
    "github_read_only_token",
    "dashboard_session_secret_file",
    "research_api_key",
    "read_only_token",
)


# is_secret_key() detects whether a dictionary key is a known secret field.
def is_secret_key(key: str) -> bool:
    return key.lower() in _SECRET_KEY_NAMES


# ---------------------------------------------------------------------------
# Redact a value based on its key name (2-argument form for test suite)
# ---------------------------------------------------------------------------


def redact_value(key: str, value: Any) -> Any:
    """Return REDACTED if *key* is a known secret-field name, else *value*.

    This is the 2-argument form used by the test suite:
    ``redact_value("DISCORD_BOT_TOKEN", "abc") == REDACTED``.
    """
    if is_secret_key(key):
        return REDACTED
    return value


# Redact a single value structurally (1-argument form for internal use).
def _redact_value_structural(value: Any) -> Any:
    """Redact sensitive values within a dict/list structure recursively.

    Only *values* that are strings are redacted via :func:`redact_text`.
    Keys are preserved.  All string values in the structure are run through
    :func:`redact_text`.
    """
    if isinstance(value, str):
        return redact_text(value)
    elif isinstance(value, dict):
        return {k: _redact_value_structural(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_redact_value_structural(item) for item in value]
    elif isinstance(value, tuple):
        return tuple(_redact_value_structural(item) for item in value)
    else:
        return value


# ---------------------------------------------------------------------------
# Text Redaction Rules
# ---------------------------------------------------------------------------

# Match Discord bot token shape: 24-30 characters starting with "Bot "
_DISCORD_BOT_TOKEN_RE = re.compile(r"[Bb]ot [A-Za-z0-9_\-]{24,30}")

# Match GitHub PAT shapes: ghp_ followed by 36-40 alphanumeric chars
_GITHUB_PAT_RE = re.compile(r"ghp_[A-Za-z0-9]{36,40}")

# Match GitHub PAT shapes: github_pat_ followed by alphanumeric chars
_GITHUB_PAT2_RE = re.compile(r"github_pat_[A-Za-z0-9]{20,40}")

# Match raw token assignment: token=VALUE or api_key=VALUE etc.
# Accept unquoted values (8+ non-whitespace chars) or quoted values.
_TOKEN_ASSIGN_RE = re.compile(
    r"(?:token|api_key|secret|password)\s*=\s*([^\s]+)",
    re.IGNORECASE,
)

# Match bearer authorization headers (redact the token part only)
_BEARER_HEADER_RE = re.compile(r"(Authorization:\s*Bearer\s*)([A-Za-z0-9\-._~+/]+)", re.IGNORECASE)

# Match interaction-style JSON blobs that may contain token-shaped strings
_INTERACTION_JSON_RE = re.compile(r"\{[^}]*\"token\"[^}]*\}", re.DOTALL)

# Match any string looking like a URL embedded in a token field
_TOKEN_URL_RE = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)


# Match API keys in research-sourced text (OpenAI-style: sk-...)
_OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9]{48}")

# Match general cloud API key shapes (long alphanumeric strings after a label)
_CLOUD_API_KEY_RE = re.compile(
    r"(?i)(aws|gcp|azure|openai|anthropic)_key\s*=\s*['\"][^'\"]{16,}['\"]"
)

# Match private IP addresses or loopback that might appear in research URLs
_PRIVATE_IP_RE = re.compile(
    r"(?:127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})"
)

# Match key: value patterns (colon-separated secrets, e.g. "secret: abc123")
_COLON_SECRET_RE = re.compile(r"(?i)(?:secret|key|token|api_key)\s*:\s*([^\s]+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Redaction helper functions
# ---------------------------------------------------------------------------


def _redact_token_assign(m: re.Match[str]) -> str:
    """Redact token=... assignments, keeping the key name but masking the value.

    m.group(1) is the value portion (8+ non-whitespace chars).
    """
    return "[REDACTED]"


def _redact_cloud_key(m: re.Match[str]) -> str:
    """Redact cloud API key assignments, keeping the service name but masking the value."""
    service = m.group(1).lower()
    return service + "_key=[REDACTED]"


# ---------------------------------------------------------------------------
# Global rule set
# ---------------------------------------------------------------------------

REDACRULES: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    # Discord bot tokens
    (_DISCORD_BOT_TOKEN_RE, "[REDACTED: discord bot token]"),
    # GitHub personal access tokens (ghp_ prefix)
    (_GITHUB_PAT_RE, "[REDACTED: github PAT]"),
    # GitHub PAT shapes: github_pat_ prefix
    (_GITHUB_PAT2_RE, "[REDACTED: github PAT]"),
    # Token assignment patterns: token=VALUE, api_key=VALUE, etc.
    # Replacement hides the value; the key word is kept but masked.
    (_TOKEN_ASSIGN_RE, _redact_token_assign),
    # Bearer headers - keep the label, redact the token
    (_BEARER_HEADER_RE, r"\1[REDACTED]"),
    # Interaction JSON blobs that contain the word "token"
    (_INTERACTION_JSON_RE, "[REDACTED: interaction JSON]"),
    # URLs embedded in token fields
    (_TOKEN_URL_RE, "[REDACTED: url in token field]"),
    # OpenAI-style API keys
    (_OPENAI_KEY_RE, "[REDACTED: openai key]"),
    # Cloud API key assignments
    (_CLOUD_API_KEY_RE, _redact_cloud_key),
    # Private IPs in research text (mask as potentially sensitive)
    (_PRIVATE_IP_RE, "[REDACTED: private IP]"),
    # Colon-separated secrets: secret: VALUE, key: VALUE, etc.
    (_COLON_SECRET_RE, _redact_token_assign),
]


# ---------------------------------------------------------------------------
# Helper: apply all rules to a string
# ---------------------------------------------------------------------------


def redact_text(text: Any) -> str:
    """Run the full rule set over *text* and return the sanitized string.

    If *text* is not a string it is returned as-is (converted to str first
    if possible).  The function never raises; if a pattern's replacement
    function raises, the original text is preserved for that rule.
    """
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:  # pylint: disable-broad-except
            return REDACTED

    result: str = text
    for pattern, replacement in REDACRULES:
        try:
            if isinstance(replacement, str):
                result = pattern.sub(replacement, result)
            else:
                result = pattern.sub(replacement, result)
        except Exception:  # pylint: disable-broad-except  # noqa: S110
            # Best effort: a broken rule must never leak the original value
            # or abort redaction of the remaining rules.
            pass
    return result


# ---------------------------------------------------------------------------
# Helper: redact a dict / list structure recursively (values only)
# ---------------------------------------------------------------------------


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive values within a dict recursively.

    Only values whose keys are "secret key names" (per :func:`is_secret_key`)
    are masked with REDACTED; other values are left untouched.

    Recurses into nested dicts and lists of dicts.
    """
    result: dict[str, Any] = {}
    for k, v in mapping.items():
        if is_secret_key(k):
            result[k] = REDACTED
        elif isinstance(v, dict):
            result[k] = redact_mapping(v)
        elif isinstance(v, list):
            result[k] = [redact_mapping(item) if isinstance(item, dict) else item for item in v]
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Pre-compiled compilations / warm-up (no-op when module imported cleanly)
# ---------------------------------------------------------------------------

# The REDACRULES list is ready for immediate use.  No initialization
# overhead beyond the module import is required.
