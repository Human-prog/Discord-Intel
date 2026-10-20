"""Security module for Phase 5 — Authentication, Authorization, and Threat Model.

Exports the core security primitives that every component must use:

- Authentication: AuthContext, authenticate_from_interaction, require_authentication
- Authorization: AuthorizationChecker, make_checker, check_* methods
- Rate limiting: rate_limiter (global instance), RateLimiter class
- Redaction: redact_text, redact_value

All functions and classes are documented in their respective modules.
"""

from __future__ import annotations

from .authentication import AuthContext, AuthError, require_authentication, authenticate_from_interaction  # noqa: F401
from .authorization import AuthorizationChecker, AuthorizationError, make_checker  # noqa: F401
from .rate_limits import rate_limiter, RateLimiter, DEFAULT_RATE_LIMITS  # noqa: F401
from .redaction import REDACTED, is_secret_key, redact_mapping, redact_text, redact_value  # noqa: F401