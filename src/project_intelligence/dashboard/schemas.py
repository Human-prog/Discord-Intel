"""Schema models for Phase 7 Dashboard API.

All models use Pydantic v2 with strict typing.  Responses are secret-free by
construction; sensitive fields never appear in output.  Enums are used for
status fields to ensure consistent values.

Typical use: a request/response cycle goes through centralized auth (Phase 5)
before reaching these schemas.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class HealthStatus(str, Enum):
    healthy = "healthy"
    stale = "stale"
    unhealthy = "unhealthy"
    unknown = "unknown"


class ProjectStatus(str, Enum):
    active = "active"
    archived = "archived"


class MilestoneStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"


class EvidenceStatus(str, Enum):
    verified = "verified"
    stale = "stale"
    conflicting = "conflicting"


class ActivityType(str, Enum):
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
    description: Optional[str] = Field(None, description="Short description")
    allowed_root: str
    status: HealthStatus = HealthStatus.unknown
    milestone_count: int = Field(0, ge=0)
    evidence_count: int = Field(0, ge=0)
    last_checked: str  # ISO-8601 UTC

    @root_validator(skip_on_failure=True)
    def enforce_readonly(cls, values: dict[str, Any]) -> dict[str, Any]:
        # Ensure the model cannot be used for writes; this is purely a summary.
        return values


class MilestoneSummary(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: MilestoneStatus
    target_date: Optional[str] = None  # ISO-8601 UTC or None
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
    uptime_seconds: Optional[float] = None

    model_config = {"json_schema_extra": {"example": {
        "app_env": "development",
        "app_log_level": "INFO",
        "database_healthy": True,
        "dashboard_bound_host": "127.0.0.1",
        "dashboard_bound_port": 8765,
        "ollama_configured": True,
        "research_configured": False,
        "uptime_seconds": 3600.5,
    }}}


class ProjectListItem(BaseModel):
    """A single line from the project list endpoint."""

    id: int
    name: str
    allowed_root: str
    status: HealthStatus
    last_checked: str


class ProjectDetail(BaseModel):
    """Full project detail response."""

    id: int
    name: str
    description: Optional[str] = None
    allowed_root: str
    status: HealthStatus
    created_at_utc: str
    updated_at_utc: str
    milestone_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    discord_mappings: int = Field(ge=0, description="Number of registered Discord mappings")
    health_freshness: str = Field(
        description="How recent the health snapshot is; one of 'fresh','stale','unknown'"
    )


class MilestoneListItem(BaseModel):
    """A single milestone from the list endpoint."""

    id: int
    project_id: int
    title: str
    status: MilestoneStatus
    target_date: Optional[str] = None


class EvidenceDetail(BaseModel):
    """Full evidence record response (source-referenced)."""

    id: int
    project_id: int
    title: str
    content_hash: str
    retrieved_at_utc: str
    confidence: float
    claim: Optional[str] = None
    is_stale: bool
    relevance_score: float = Field(ge=0.0, le=1.0)


class ActivityEntry(BaseModel):
    """A single recent-activity entry."""

    id: int
    type: ActivityType
    project_id: Optional[int] = None
    title: str
    occurred_at_utc: str
    actor: Optional[str] = None  # Discord user mention or "system"
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pagination and query schemas
# ---------------------------------------------------------------------------

class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="1-based page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")

    @root_validator(skip_on_failure=True)
    def ensure_consistent_page(cls, values: dict[str, Any]) -> dict[str, Any]:
        # If per_page is set to an extreme value, cap the effective page range.
        return values


class ProjectSearchParams(BaseModel):
    """Query parameters for project search/filter."""

    name: Optional[str] = None
    status: Optional[HealthStatus] = None
    min_evidence: Optional[int] = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Error response schema
# ---------------------------------------------------------------------------

class DashboardError(BaseModel):
    """Standard error response — never contains secrets or stack traces."""

    error: str = Field(description="Machine-readable error kind")
    message: str = Field(description="Human-readable explanation")
    correlation_id: Optional[str] = Field(default=None, description="Track across requests")
    timestamp_utc: str = Field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat() + "Z")

    model_config = {"json_schema_extra": {"example": {
        "error": "unauthorized",
        "message": "Authentication required or denied",
        "correlation_id": "c1d2e3f4-5678-90ab-cd-ef1234567890",
        "timestamp_utc": "2026-10-17T12:34:56.789Z",
    }}}


# ---------------------------------------------------------------------------
# State / loading schemas (for frontend use)
# ---------------------------------------------------------------------------

class LoadingState(BaseModel):
    """Minimal state object shown while dashboard data is loading."""

    loading: bool = True
    error: Optional[str] = None
    last_refreshed: str = Field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat() + "Z")


class EmptyState(BaseModel):
    """Minimal state object shown when no data matches the current filter."""

    message: str
    suggestion: Optional[str] = None


class UnauthorizedState(BaseModel):
    """State shown when the user is not authorized for the requested resource."""

    reason: str
    contact: Optional[str] = None  # e.g., "contact an owner"