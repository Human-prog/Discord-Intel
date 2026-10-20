"""Read-only dashboard API for Discord Project Intelligence (Phase 7).

Provides a private, responsive dashboard accessible from an authorized device.
Bound to loopback by default; remote access via Tailscale Serve with application
(owner-session) authentication only.

The FastAPI application lives in :mod:`project_intelligence.dashboard.dashboard`
and is exposed lazily here so importing the package does not eagerly construct
the app (and stays free of import cycles).
"""

from __future__ import annotations

from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from .dashboard import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
