"""Schema models for Phase 7 Dashboard API.

All models use Pydantic v2 with strict typing.  Responses are secret-free by
construction; sensitive fields never appear in output.  Enums are used for
status fields to ensure consistent values.

Typical use: a request/response cycle goes through centralized auth (Phase 5)
before reaching these schemas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    """Return the current time as an ISO-8601 UTC string."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class HealthStatus(StrEnum):
    healthy = "healthy"
    stale = "stale"
    unhealthy = "unhealthy"
    unknown = "unknown"


class ProjectStatus(StrEnum):
    active = "active"
    archived = "archived"


class MilestoneStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"


class EvidenceStatus(StrEnum):
    verified = "verified"
    stale = "stale"
    conflicting = "conflicting"


class ActivityType(StrEnum):
    note = "note"
    milestone = "milestone"
    evidence = "evidence"
    research = "research"


# ---------------------------------------------------------------------------
# Core entity summaries (read-only; IDs only, no nested payloads)
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
    id: int
    name: str
    description: str | None = Field(None, description="Short description")
    allowed_root: str
    status: HealthStatus = HealthStatus.unknown
    milestone_count: int = Field(0, ge=0)
    evidence_count: int = Field(0, ge=0)
    last_checked: str  # ISO-8601 UTC


class MilestoneSummary(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: MilestoneStatus
    target_date: str | None = None  # ISO-8601 UTC or None
    created_at: str  # ISO-8601 UTC


class EvidenceSummary(BaseModel):
    id: int
    title: str
    content_hash: str  # SHA-256 or similar; never the raw content
    retrieved_at_utc: str  # ISO-8601 UTC
    confidence: float = Field(ge=0.0, le=1.0)
    is_stale: bool = False


# ---------------------------------------------------------------------------
# Dashboard response schemas
# ---------------------------------------------------------------------------


class DashboardHealth(BaseModel):
    """Overall application health status."""

    app_env: str = Field(default="development", description="development|testing|production")
    app_log_level: str = Field(default="INFO", description="DEBUG|INFO|WARNING|ERROR|CRITICAL")
    database_healthy: bool = True
    dashboard_bound_host: str
    dashboard_bound_port: int
    ollama_configured: bool
    research_configured: bool
    uptime_seconds: float | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "app_env": "development",
                "app_log_level": "INFO",
                "database_healthy": True,
                "dashboard_bound_host": "127.0.0.1",
                "dashboard_bound_port": 8765,
                "ollama_configured": True,
                "research_configured": False,
                "uptime_seconds": 3600.5,
            }
        }
    }


class ProjectListItem(BaseModel):
    """A single line from the project list endpoint."""

    id: int
    name: str
    description: str | None = None
    allowed_root: str
    status: HealthStatus
    last_checked: str
    catalog_status: str | None = None
    category: str | None = None
    priority: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    source: str = "manual"
    monitored: bool = True
    last_activity_utc: str | None = None
    work_item_count: int = Field(default=0, ge=0)
    repo_url: str | None = None


class WorkItemSummary(BaseModel):
    """One unit of work recorded against a project."""

    id: int
    project_id: int
    work_type: str
    title: str
    body: str | None = None
    status: str
    source: str
    occurred_at_utc: str | None = None


class ResearchSourceSummary(BaseModel):
    id: int
    title: str
    url: str | None = None
    source_type: str
    snippet: str | None = None
    relevance_score: float = 0.0
    source_ref: str | None = None
    retrieved_at_utc: str


class ResearchJobSummary(BaseModel):
    id: int
    project_id: int | None = None
    project_name: str | None = None
    question: str
    status: str
    scope: str
    provider: str | None = None
    started_at_utc: str
    completed_at_utc: str | None = None
    result_summary: str | None = None
    source_count: int = Field(default=0, ge=0)
    error: str | None = None


class ResearchJobDetail(ResearchJobSummary):
    report_text: str | None = None
    report_generated_at_utc: str | None = None
    sources: list[ResearchSourceSummary] = Field(default_factory=list)


class CatalogSummary(BaseModel):
    project_count: int = Field(default=0, ge=0)
    monitored_count: int = Field(default=0, ge=0)
    catalog_count: int = Field(default=0, ge=0)
    active_count: int = Field(default=0, ge=0)
    work_item_count: int = Field(default=0, ge=0)
    research_job_count: int = Field(default=0, ge=0)
    categories: list[str] = Field(default_factory=list)
    last_import_at_utc: str | None = None


class ProjectDetail(BaseModel):
    """Full project detail response."""

    id: int
    name: str
    description: str | None = None
    allowed_root: str
    status: HealthStatus
    created_at_utc: str
    updated_at_utc: str
    milestone_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    discord_mappings: int = Field(ge=0, description="Number of registered Discord mappings")
    health_freshness: str = Field(description="How recent the health snapshot is; one of 'fresh','stale','unknown'")
    catalog_status: str | None = None
    category: str | None = None
    priority: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    repo_url: str | None = None
    local_path: str | None = None
    source: str = "manual"
    monitored: bool = True
    last_activity_utc: str | None = None
    work_item_count: int = Field(default=0, ge=0)
    research_count: int = Field(default=0, ge=0)
    recent_work: list[WorkItemSummary] = Field(default_factory=list)
    recent_research: list[ResearchJobSummary] = Field(default_factory=list)


class MilestoneListItem(BaseModel):
    """A single milestone from the list endpoint."""

    id: int
    project_id: int
    title: str
    status: MilestoneStatus
    target_date: str | None = None


class EvidenceDetail(BaseModel):
    """Full evidence record response (source-referenced)."""

    id: int
    project_id: int
    title: str
    content_hash: str
    retrieved_at_utc: str
    confidence: float
    claim: str | None = None
    is_stale: bool
    relevance_score: float = Field(ge=0.0, le=1.0)


class ActivityEntry(BaseModel):
    """A single recent-activity entry."""

    id: int
    type: ActivityType
    project_id: int | None = None
    title: str
    occurred_at_utc: str
    actor: str | None = None  # Discord user mention or "system"
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pagination and query schemas
# ---------------------------------------------------------------------------


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="1-based page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")


class ProjectSearchParams(BaseModel):
    """Query parameters for project search/filter."""

    name: str | None = None
    status: HealthStatus | None = None
    min_evidence: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Error response schema
# ---------------------------------------------------------------------------


class DashboardError(BaseModel):
    """Standard error response - never contains secrets or stack traces."""

    error: str = Field(description="Machine-readable error kind")
    message: str = Field(description="Human-readable explanation")
    correlation_id: str | None = Field(default=None, description="Track across requests")
    timestamp_utc: str = Field(default_factory=_utc_now_iso)

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "unauthorized",
                "message": "Authentication required or denied",
                "correlation_id": "c1d2e3f4-5678-90ab-cd-ef1234567890",
                "timestamp_utc": "2026-10-17T12:34:56.789Z",
            }
        }
    }


# ---------------------------------------------------------------------------
# State / loading schemas (for frontend use)
# ---------------------------------------------------------------------------


class LoadingState(BaseModel):
    """Minimal state object shown while dashboard data is loading."""

    loading: bool = True
    error: str | None = None
    last_refreshed: str = Field(default_factory=_utc_now_iso)


class EmptyState(BaseModel):
    """Minimal state object shown when no data matches the current filter."""

    message: str
    suggestion: str | None = None


class UnauthorizedState(BaseModel):
    """State shown when the user is not authorized for the requested resource."""

    reason: str
    contact: str | None = None  # e.g., "contact an owner"
