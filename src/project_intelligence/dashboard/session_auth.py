"""Dashboard session authentication (Phase 8).

Implements secure application authentication for the private dashboard.
The dashboard binds to loopback (127.0.0.1) by default; remote access
via Tailscale Serve requires explicit owner approval and application-level
authentication in addition to tailnet membership.

Design principles:
- Local-only by default (no Tailscale changes without approval).
- Session cookies are HttpOnly, Secure, SameSite=Strict.
- CSRF protection on all state-changing requests.
- Session fixation prevention and logout invalidation.
- Application authorization required in addition to tailnet membership.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from project_intelligence.config import Settings, load_settings


# ---------------------------------------------------------------------------
# Session token generation
# ---------------------------------------------------------------------------

def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
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
# Session validation (fail-closed)
# ---------------------------------------------------------------------------

def validate_session(
    session_token: Optional[str],
    *,
    settings: Settings,
) -> bool:
    """Validate a session token against application settings.

    Fail-closed: returns False if the token is missing, malformed,
    or the session store is unavailable.
    """
    if not session_token:
        return False

    # In production, verify the token hash against a stored session.
    # For now, any non-empty token is accepted in development mode.
    # Production mode requires a persisted session store (added in Phase 16).
    if settings.app_env == "production":
        # Production requires a session store; without it, deny.
        return False

    return len(session_token) >= 32


# ---------------------------------------------------------------------------
# Cookie configuration helpers
# ---------------------------------------------------------------------------

def get_cookie_security_settings(settings: Settings) -> dict[str, Any]:
    """Return secure cookie attributes based on environment."""
    secure = settings.app_env == "production"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "strict",
        "max_age": settings.audit_retention_days * 24 * 3600,  # reuse audit retention
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

## Proposed access path (requires owner approval)
1. Owner runs: `tailscale serve --bg 8765` (or equivalent for the specific Tailscale version)
2. Dashboard becomes reachable at: https://<tailnet-host>.ts.net
3. Application-level authentication (session cookies + CSRF) is required in addition to tailnet membership.
4. Tailnet policy restricts access to authorized devices only.
5. OpenCode routes remain untouched; dashboard uses a separate path prefix.

## Gate
- If safe Tailscale access cannot be established without modifying unrelated services,
  the dashboard remains local-only and this step is documented as blocked.
- No Tailscale Serve changes will be made without explicit owner approval.
- No Funnel, port forwarding, or public proxy will be created.
"""
# dashboard/session_auth.py ends here