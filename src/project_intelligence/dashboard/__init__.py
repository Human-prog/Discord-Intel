"""Read-only dashboard API for Discord Project Intelligence (Phase 7).

Provides a private, responsive dashboard accessible from an authorized device.
Bound to loopback by default; remote access via Tailscale Serve with application
authentication only.

Endpoints are all GET-style read operations; no mutating administrative endpoints
are exposed to unauthenticated or remote users.
"""

from __future__ import annotations

__all__ = [
    "app",
    "get_dashboard_stats",
    "get_project_list",
    "get_project_detail",
    "get_milestones",
    "get_evidence",
    "get_recent_activity",
]