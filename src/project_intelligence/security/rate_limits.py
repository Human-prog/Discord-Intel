"""Rate limiting (Phase 5).

Provides per-user, per-guild, and per-command rate limiting with a sliding
window algorithm.  Limits are configured via the application Settings and
enforced by the AuthorizationChecker or a dedicated middleware.

The store is in-memory, keyed by Discord IDs.  For multi-process deployments
a distributed store (Redis, etc.) can be swapped in without changing the
interface.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import field
from time import monotonic
from typing import Any, DefaultDict, Dict, List, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class RateLimitRecord(NamedTuple):
    """One entry in the sliding window for a single key."""

    timestamps: List[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per‑category limits (configured from Settings)
# ---------------------------------------------------------------------------

#: Default rate limits when the field is not explicitly overridden.
#  Keys map to Settings field names; values are (max_requests, window_seconds).
DEFAULT_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "command_per_user": (5, 60),       # 5 commands per user per 60s
    "command_per_guild": (10, 60),     # 10 commands per guild per 60s
    "command_per_channel": (10, 60),   # 10 commands per channel per 60s
    "research_per_user": (3, 3600),    # 3 research jobs per user per hour
    "health_check_per_hour": (60, 3600),  # 60 health checks per hour
}


# -------------------------------------------------------------------------__
# Sliding‑window rate‑limit store (in‑memory, process‑local)
# ---------------------------------------------------------------------------

_redis_like: Optional[Any] = None  # placeholder for future distributed store


class RateLimiter:
    """Sliding‑window rate limiter for Discord bot commands.

    Each ``key`` (typically a Discord snowflake integer) gets its own window.
    Requests outside the window are allowed; requests inside the window are
    denied until the oldest timestamp slides out.

    Usage::
        limiter = RateLimiter()
        allowed, reset = limiter.is_rate_limited(key, limit, window)
    """

    def __init__(self, max_keys: int = 10_000) -> None:
        self._windows: DefaultDict[int, RateLimitRecord] = defaultdict(
            RateLimitRecord
        )
        self._max_keys = max_keys

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def is_rate_limited(
        self,
        key: int,
        limit: int,
        window: float,
    ) -> Tuple[bool, float]:
        """Return ``(True, reset_time)`` if the key exceeds *limit* within
        *window* seconds.  Otherwise return ``(False, reset_time)`` where
        *reset_time* is the epoch seconds when the next request will be
        allowed.

        The algorithm:

        1. Prune timestamps older than ``now - window``.
        2. If the remaining count >= *limit*, the request is limited.
        3. Otherwise, record ``now`` and return ``(False, next_reset)``.
        """
        now = monotonic()
        record = self._windows[key]

        # Prune stale timestamps
        timestamps = [t for t in record.timestamps if now - t < window]
        if len(timestamps) >= limit:
            # Limited: return the time when the oldest entry slides out
            reset = timestamps[0] + window
            return True, reset

        # Record this request
        timestamps.append(now)
        # Keep the list bounded (prevent unbounded growth from long‑running processes)
        if len(timestamps) > self._max_keys:
            # Keep the most recent entries
            timestamps = timestamps[-self._max_keys :]

        self._windows[key] = RateLimitRecord(timestamps=timestamps)
        # Reset time is the earliest moment a slot opens up; for a sliding
        # window this is ``now - window + epsilon``, but we simply return
        # ``now`` so the client can immediately retry.
        return False, now

    # ------------------------------------------------------------------
    # Convenience methods for the common limit categories
    # ------------------------------------------------------------------

    def check_command_per_user(self, user_id: int) -> Tuple[bool, float]:
        """Check the per-user command limit.  Returns ``(limited, reset)``."""
        return self.is_rate_limited(user_id, *DEFAULT_RATE_LIMITS["command_per_user"])

    def check_command_per_guild(self, guild_id: int) -> Tuple[bool, float]:
        """Check the per-guild command limit.  Returns ``(limited, reset)``."""
        return self.is_rate_limited(guild_id, *DEFAULT_RATE_LIMITS["command_per_guild"])

    def check_command_per_channel(self, channel_id: int) -> Tuple[bool, float]:
        """Check the per-channel command limit.  Returns ``(limited, reset)``."""
        return self.is_rate_limited(channel_id, *DEFAULT_RATE_LIMITS["command_per_channel"])

    def check_research_per_user(self, user_id: int) -> Tuple[bool, float]:
        """Check the per-user research-job limit.  Returns ``(limited, reset)``."""
        return self.is_rate_limited(user_id, *DEFAULT_RATE_LIMITS["research_per_user"])

    def check_health_per_hour(self) -> Tuple[bool, float]:
        """Placeholder: health-check rate limit.  Currently always allowed."""
        return False, monotonic()


# Global instance so the bot and dashboard can share the same limiter.
rate_limiter = RateLimiter()