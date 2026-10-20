"""Dashboard owner-session authentication (Phase 8 / Phase 7 UI).

The dashboard binds to loopback (127.0.0.1) by default; remote access goes
through Tailscale Serve, which is tailnet-only.  Tailnet membership alone is
not application authentication, so the dashboard additionally requires an
owner session.

Design:
- The owner secret lives in ``DASHBOARD_SESSION_SECRET_FILE`` (production
  requires this file; it is provisioned with mode 0640, root:dpi).
- Signing in means presenting that secret once over HTTPS; the server then
  issues a stateless, HMAC-SHA256-signed session token in an HttpOnly,
  SameSite=Strict cookie.  No plaintext secret is stored in the cookie.
- Tokens expire after ``SESSION_TTL_SECONDS``; rotating the secret file
  invalidates every outstanding session.
- Cookie-authenticated requests are accepted for safe (read-only) HTTP
  methods only, so there are no state-changing cookie endpoints to CSRF.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path
from typing import Any

from project_intelligence.config import Settings
from project_intelligence.security.authentication import AuthContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_COOKIE_NAME = "dpi_owner_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30 days
_TOKEN_VERSION = "v1"  # noqa: S105 - token format version, not a credential
_MIN_SECRET_LENGTH = 32


class SessionAuthError(Exception):
    """Raised when session authentication cannot proceed. Never contains secrets."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Session token generation (legacy helpers, still used by tests/tools)
# ---------------------------------------------------------------------------


def generate_session_token() -> str:
    """Generate a cryptographically secure random session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash a session token for storage (never store raw tokens)."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# CSRF token generation
# ---------------------------------------------------------------------------


def generate_csrf_token() -> str:
    """Generate a CSRF token for form submissions."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(stored: str, provided: str) -> bool:
    """Verify a CSRF token using constant-time comparison."""
    return hmac.compare_digest(stored, provided)


# ---------------------------------------------------------------------------
# Owner secret loading
# ---------------------------------------------------------------------------


def load_owner_secret(settings: Settings) -> bytes:
    """Read and validate the owner secret from disk.

    Fail-closed: raises SessionAuthError if the configured file is missing,
    unreadable, or too short.  The file is never included in error messages.
    """
    secret_file = settings.dashboard_session_secret_file
    if secret_file is None:
        raise SessionAuthError("dashboard session secret is not configured")

    path = Path(secret_file)
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SessionAuthError("dashboard session secret file is unreadable") from exc

    if len(raw) < _MIN_SECRET_LENGTH:
        raise SessionAuthError("dashboard session secret is too short")
    return raw.encode()


# ---------------------------------------------------------------------------
# Stateless signed session tokens
# ---------------------------------------------------------------------------


def _sign(secret: bytes, payload: str) -> str:
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def issue_session_token(settings: Settings) -> tuple[str, int]:
    """Create a signed session token.

    Returns ``(token, expires_at_epoch_seconds)``.  Raises SessionAuthError
    when no usable owner secret is configured.
    """
    secret = load_owner_secret(settings)
    expires = int(time.time()) + SESSION_TTL_SECONDS
    nonce = secrets.token_urlsafe(16)
    payload = f"{_TOKEN_VERSION}|{expires}|{nonce}"
    token = f"{_TOKEN_VERSION}.{expires}.{nonce}.{_sign(secret, payload)}"
    return token, expires


def verify_session_token(token: str | None, settings: Settings) -> bool:
    """Verify a signed session token.  Fail-closed on any problem."""
    if not token:
        return False

    parts = token.split(".")
    if len(parts) != 4:
        return False

    version, expires_raw, nonce, signature = parts
    if version != _TOKEN_VERSION:
        return False

    try:
        expires = int(expires_raw)
    except ValueError:
        return False

    now = int(time.time())
    if expires <= now:
        return False
    # Reject tokens that claim to live longer than the configured lifetime.
    if expires > now + SESSION_TTL_SECONDS + 60:
        return False

    try:
        secret = load_owner_secret(settings)
    except SessionAuthError:
        return False

    expected = _sign(secret, f"{_TOKEN_VERSION}|{expires}|{nonce}")
    return hmac.compare_digest(expected, signature)


def verify_owner_secret(candidate: str, settings: Settings) -> bool:
    """Constant-time comparison of a presented secret against the file."""
    if not candidate:
        return False
    try:
        secret = load_owner_secret(settings)
    except SessionAuthError:
        return False
    return hmac.compare_digest(secret, candidate.encode())


def owner_auth_context(settings: Settings) -> AuthContext:
    """Build an owner AuthContext for a verified dashboard session.

    Owner sessions bypass Discord guild/channel scoping by construction
    (``auth_via='owner_session'``); the IDs are placeholders because there is
    no Discord interaction behind a browser request.
    """
    owner_id = settings.discord_owner_user_ids[0] if settings.discord_owner_user_ids else 0
    return AuthContext(
        discord_user_id=owner_id,
        discord_guild_id=0,
        discord_channel_id=0,
        auth_via="owner_session",
    )


# ---------------------------------------------------------------------------
# Session validation (kept for API compatibility with earlier phases)
# ---------------------------------------------------------------------------


def validate_session(
    session_token: str | None,
    *,
    settings: Settings,
) -> bool:
    """Validate a session token; fail-closed if missing, malformed, or stale."""
    return verify_session_token(session_token, settings)


# ---------------------------------------------------------------------------
# Cookie configuration helpers
# ---------------------------------------------------------------------------


def get_cookie_security_settings(settings: Settings) -> dict[str, Any]:
    """Return secure cookie attributes based on environment."""
    return {
        "httponly": True,
        # Secure cookies require HTTPS.  Production is served over Tailscale
        # HTTPS; development over plain loopback HTTP must not set Secure or
        # the browser would discard the cookie.
        "secure": settings.app_env == "production",
        "samesite": "strict",
        "max_age": SESSION_TTL_SECONDS,
        "path": "/",
    }


# ---------------------------------------------------------------------------
# Tailnet policy documentation (no runtime changes)
# ---------------------------------------------------------------------------

TAILNET_POLICY_DOC = """
# Dashboard Tailscale Access Policy (Phase 8)

## Current state
- Dashboard binds to 127.0.0.1:8765 (loopback only).
- Tailscale Serve configuration: **NOT MODIFIED** (existing routes preserved).
- OpenCode routes: **PRESERVED** (no changes made).
- Funnel: **DISABLED** (not enabled).
- Port forwarding: **NOT CONFIGURED** (no router changes).
- Public exposure: **NONE** (no public endpoints).

## Access path (owner approved)
1. Owner runs: `tailscale serve --bg 8765`
2. Dashboard is reachable at: https://<tailnet-host>.ts.net
3. Application-level authentication (owner session cookie) is required in
   addition to tailnet membership.
4. Tailnet policy restricts access to authorized devices only.
5. OpenCode routes remain untouched; the dashboard is a separate node route.

## Gate
- If safe Tailscale access cannot be established without modifying unrelated
  services, the dashboard remains local-only and this step is documented as
  blocked.
- No Tailscale Serve changes are made without explicit owner approval.
- No Funnel, port forwarding, or public proxy is created.
"""
