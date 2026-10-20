"""Sliding-window rate limiter tests (Phase 5)."""

from __future__ import annotations

import pytest

import project_intelligence.security.rate_limits as rate_limits
from project_intelligence.security.rate_limits import DEFAULT_RATE_LIMITS, RateLimiter


def test_per_user_limit_allows_five_then_blocks() -> None:
    limiter = RateLimiter()
    limit, _window = DEFAULT_RATE_LIMITS["command_per_user"]

    for _ in range(limit):
        limited, _reset = limiter.check_command_per_user(42)
        assert limited is False

    limited, reset = limiter.check_command_per_user(42)
    assert limited is True
    assert reset > 0


def test_different_users_have_independent_windows() -> None:
    limiter = RateLimiter()
    for _ in range(5):
        limiter.check_command_per_user(1)

    assert limiter.check_command_per_user(1)[0] is True
    assert limiter.check_command_per_user(2)[0] is False


def test_categories_do_not_share_counters() -> None:
    """Regression: command checks used to consume the research allowance."""
    limiter = RateLimiter()
    for _ in range(5):
        limiter.check_command_per_user(7)

    # A burst of commands must not exhaust the separate research budget.
    assert limiter.check_research_per_user(7)[0] is False


def test_records_have_independent_timestamp_lists() -> None:
    """Regression: NamedTuple defaults used to share one mutable list."""
    limiter = RateLimiter()
    limiter.check_command_per_user(1)
    limiter.check_command_per_user(2)

    first = limiter._windows[("command:user", 1)]
    second = limiter._windows[("command:user", 2)]
    assert first is not second
    assert len(first.timestamps) == 1
    assert len(second.timestamps) == 1


def test_window_expiry_frees_slots(monkeypatch) -> None:
    now = [1_000.0]
    monkeypatch.setattr(rate_limits, "monotonic", lambda: now[0])

    limiter = RateLimiter()
    for _ in range(5):
        assert limiter.check_command_per_user(9)[0] is False
    assert limiter.check_command_per_user(9)[0] is True

    now[0] += 61
    assert limiter.check_command_per_user(9)[0] is False


def test_guild_limit() -> None:
    limiter = RateLimiter()
    limit, _ = DEFAULT_RATE_LIMITS["command_per_guild"]
    for _ in range(limit):
        assert limiter.check_command_per_guild(5)[0] is False
    assert limiter.check_command_per_guild(5)[0] is True


def test_channel_limit() -> None:
    limiter = RateLimiter()
    limit, _ = DEFAULT_RATE_LIMITS["command_per_channel"]
    for _ in range(limit):
        assert limiter.check_command_per_channel(5)[0] is False
    assert limiter.check_command_per_channel(5)[0] is True


def test_research_limit() -> None:
    limiter = RateLimiter()
    limit, _ = DEFAULT_RATE_LIMITS["research_per_user"]
    for _ in range(limit):
        assert limiter.check_research_per_user(3)[0] is False
    assert limiter.check_research_per_user(3)[0] is True


def test_health_limit_is_global() -> None:
    limiter = RateLimiter()
    limit, _ = DEFAULT_RATE_LIMITS["health_check_per_hour"]
    for _ in range(limit):
        assert limiter.check_health_per_hour()[0] is False
    assert limiter.check_health_per_hour()[0] is True


def test_reset_time_points_at_window_slide(monkeypatch) -> None:
    now = [2_000.0]
    monkeypatch.setattr(rate_limits, "monotonic", lambda: now[0])

    limiter = RateLimiter()
    for _ in range(5):
        limiter.check_command_per_user(11)

    limited, reset = limiter.check_command_per_user(11)
    assert limited is True
    assert reset == pytest.approx(2_000.0 + 60)


def test_timestamp_list_is_trimmed_to_bound() -> None:
    limiter = RateLimiter(max_keys=3)
    limited, reset = limiter.is_rate_limited("key", limit=10, window=100)
    assert limited is False
    assert reset > 0

    # Record three additional hits; the stored list stays bounded at max_keys.
    for _ in range(3):
        limiter.is_rate_limited("key", limit=10, window=100)
    assert len(limiter._windows["key"].timestamps) <= 3
