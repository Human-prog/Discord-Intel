"""Unit coverage for dashboard helpers, handlers, and the milestone write path."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from project_intelligence.dashboard import dashboard
from project_intelligence.dashboard.schemas import MilestoneStatus
from project_intelligence.security.authentication import AuthError
from project_intelligence.security.authorization import AuthorizationError
from project_intelligence.storage import repositories as repo

# ---------------------------------------------------------------------------
# Parsing and freshness helpers
# ---------------------------------------------------------------------------


def test_parse_utc_accepts_z_suffix_and_offsets() -> None:
    assert dashboard._parse_utc("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, tzinfo=UTC)
    assert dashboard._parse_utc("2026-01-01T00:00:00+00:00") == datetime(2026, 1, 1, tzinfo=UTC)


def test_parse_utc_returns_none_for_garbage() -> None:
    assert dashboard._parse_utc("not-a-date") is None


def test_health_freshness_buckets() -> None:
    now = datetime.now(UTC)
    assert dashboard._health_freshness(now.isoformat()) == "fresh"
    assert dashboard._health_freshness((now - timedelta(days=2)).isoformat()) == "stale"
    assert dashboard._health_freshness((now - timedelta(days=10)).isoformat()) == "unknown"
    assert dashboard._health_freshness("garbage") == "unknown"


def test_health_status_falls_back_to_unknown() -> None:
    assert dashboard._health_status("healthy") == "healthy"
    assert dashboard._health_status("bogus") == "unknown"
    assert dashboard._health_status(None) == "unknown"


def test_milestone_status_falls_back_to_open() -> None:
    assert dashboard._milestone_status("completed") == "completed"
    assert dashboard._milestone_status("bogus") == "open"


def test_clamp_unit_bounds_values() -> None:
    assert dashboard._clamp_unit("0.5") == 0.5
    assert dashboard._clamp_unit("2") == 1.0
    assert dashboard._clamp_unit("-1") == 0.0
    assert dashboard._clamp_unit(None) == 0.0
    assert dashboard._clamp_unit(object()) == 0.0


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


def _request(correlation_id: str | None = "corr-1") -> SimpleNamespace:
    state = SimpleNamespace()
    if correlation_id is not None:
        state.correlation_id = correlation_id
    return SimpleNamespace(state=state)


def test_authorization_errors_become_403() -> None:
    response = asyncio.run(dashboard._handle_authorization_error(_request(), AuthorizationError("denied")))
    assert response.status_code == 403
    body = json.loads(response.body)
    assert body["error"] == "forbidden"
    assert body["message"] == "denied"
    assert body["correlation_id"] == "corr-1"


def test_authentication_errors_become_401() -> None:
    response = asyncio.run(dashboard._handle_auth_error(_request(None), AuthError("no session")))
    assert response.status_code == 401
    body = json.loads(response.body)
    assert body["error"] == "unauthorized"
    assert body["message"] == "no session"
    assert body["correlation_id"] is None


# ---------------------------------------------------------------------------
# Milestone write endpoint (direct invocation bypasses auth dependency)
# ---------------------------------------------------------------------------


class _StubAuth:
    def __init__(self) -> None:
        self.checked: list[int] = []

    def check_project_access(self, project_id: int) -> None:
        self.checked.append(project_id)


def test_upsert_milestone_endpoint_persists_and_returns(db) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    auth = _StubAuth()
    payload = dashboard.MilestoneCreate(
        title="Ship v1",
        description="Release",
        status=MilestoneStatus.in_progress,
        target_date="2026-12-01",
    )

    result = asyncio.run(dashboard.api_upsert_milestone(project.id, payload, auth))

    assert auth.checked == [project.id]
    assert result.title == "Ship v1"
    assert result.description == "Release"
    assert result.status == MilestoneStatus.in_progress
    assert result.target_date == "2026-12-01"

    stored = repo.list_milestones_for_project(db, project.id)
    assert len(stored) == 1
    assert stored[0].title == "Ship v1"


def test_lazy_package_export() -> None:
    import project_intelligence.dashboard as package

    assert package.app is dashboard.app
    with pytest.raises(AttributeError, match="no attribute"):
        package.__getattr__("not_a_real_attribute")


def test_tech_stack_parses_only_lists_of_strings() -> None:
    assert dashboard._tech_stack(None) == []
    assert dashboard._tech_stack("") == []
    assert dashboard._tech_stack("not-json") == []
    assert dashboard._tech_stack('{"python": true}') == []
    assert dashboard._tech_stack('["Python", "", "  ", "FastAPI"]') == ["Python", "FastAPI"]
