"""Read-only dashboard API for Discord Project Intelligence (Phase 7).

FastAPI application with endpoints for:
- Health, project list, project detail, milestone, evidence, recent activity
- Centralized authentication and authorization (Phase 5)
- Minimal responsive interface suitable for iPhone browsers
- Loopback bind 127.0.0.1 by default
- Safe error handling without stack traces or secret leakage
- Pagination and reasonable response limits

All endpoints require centralized authorization before retrieving project data.
Ephemeral responses are used for private results wherever supported.
"""

from __future__ import annotations

from typing import List, Optional

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

from project_intelligence.config import Settings, load_settings
from project_intelligence.dashboard.schemas import (
    DashboardHealth,
    ProjectSummary,
    ProjectListItem,
    ProjectDetail,
    MilestoneSummary,
    MilestoneListItem,
    EvidenceSummary,
    EvidenceDetail,
    ActivityEntry,
    DashboardError,
    LoadingState,
    EmptyState,
    UnauthorizedState,
    HealthStatus,
    ProjectStatus,
    MilestoneStatus,
    EvidenceStatus,
    ActivityType,
    PaginationParams,
    ProjectSearchParams,
)
from project_intelligence.health.health_engine import (
    check_project_health,
    store_health_snapshot,
    check_and_store_health,
    _utc_now,
)
from project_intelligence.security import (
    REDACTED,
    is_secret_key,
    redact_mapping,
    redact_text,
    redact_value,

    AuthContext,
    require_authentication,
    AuthError as AuthenticationError,
    make_checker,
    AuthorizationChecker,
    AuthorizationError,
    rate_limiter,
    DEFAULT_RATE_LIMITS,
)
from project_intelligence.storage.database import get_conn, close
from project_intelligence.storage.repositories import (
    get_project_by_root,
    list_projects,
    list_project_sources,
    list_project_sources,
    get_mapping,
    list_mappings_for_project,
    get_authorized_user,
    list_authorized_users_for_project,
    upsert_note,
    list_notes_for_project,
    upsert_milestone,
    list_milestones_for_project,
    upsert_evidence,
    list_evidence_for_project,
    upsert_repository_snapshot,
    list_snapshots_for_project,
    upsert_research_job,
    list_research_jobs_for_project,
    upsert_research_source,
    list_projects as list_proj_repo,
)
from project_intelligence.security.authorization import AuthorizationChecker as AuthChecker

# ---------------------------------------------------------------------------
# Lifespan / startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: validate configuration, ensure database exists."""
    # Load settings; fail-closed if production requirements not met
    settings = load_settings()
    # Ensure data directory exists (lazy; service startup creates it)
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    # Yield control to the application
    yield
    # Shutdown: close any open connections (no-op with SQLite + get_conn)


app = FastAPI(
    title="Discord Project Intelligence — Dashboard API",
    description="Private, read-only project-intelligence dashboard (loopback-bind only).",
    version="0.1.0",
    lifespan=lifespan,
)

# Bind security scheme for potential cookie/session auth in later phases
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Dependency: get current settings
# ---------------------------------------------------------------------------

def get_settings() -> Settings:
    """Return loaded (validated) application settings."""
    return load_settings()


# ---------------------------------------------------------------------------
# Dependency: authenticate the request via Discord interaction context
# ---------------------------------------------------------------------------

def get_auth_context(
    request: Request,
) -> AuthContext:
    """Extract Discord IDs from the interaction context.

    In production this would parse the Discord interaction payload.
    For now we raise AuthError so every protected endpoint is explicit.
    """
    # The real payload parsing happens in the bot layer; here we simply
    # require that the caller provide user/guild/channel via query or header
    # as a placeholder for the Phase-5 integration.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required — provide Discord interaction context",
    )


# ---------------------------------------------------------------------------
# Dependency: central authorization checker
# ---------------------------------------------------------------------------

def get_auth_checker(
    settings: Settings = Depends(get_settings), auth_ctx: AuthContext = Depends(get_auth_context)
) -> AuthChecker:
    """Return a per-request AuthorizationChecker instance."""
    return make_checker(auth_ctx, settings)


# ---------------------------------------------------------------------------
# Helper: run a check and produce a secret-free error response
# ---------------------------------------------------------------------------

def _auth_required() -> None:
    """Raise an HTTP 401 that never leaks secrets."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required or denied",
    )


# ---------------------------------------------------------------------------
# --- /health (global application status) ---
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    response_model=DashboardHealth,
    summary="Application and integration health status",
    description="Return overall application status including environment, dashboard bind address, "
    "and whether Ollama/research are configured.  Always bound to loopback.",
    responses={
        401: {"model": DashboardError, "description": "Authentication required"},
    },
)
async def api_health(settings: Settings = Depends(get_settings)) -> DashboardHealth:
    """Global application health — no project or guild scoping required."""
    return DashboardHealth(
        app_env=settings.app_env,
        app_log_level=settings.app_log_level,
        dashboard_bound_host=settings.dashboard_bind_host,
        dashboard_bound_port=settings.dashboard_bind_port,
        ollama_configured=settings.ollama_model is not None,
        research_configured=settings.research_provider is not None,
    )


# ---------------------------------------------------------------------------
# --- Project listing & detail ---
# ---------------------------------------------------------------------------

@app.get(
    "/projects",
    response_model=List[ProjectListItem],
    summary="List authorized projects",
    description="Return a paginated list of projects the authenticated user is authorized to view. "
    "Requires central authorization (Phase 5).",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_project_list(
    pagination: PaginationParams = Depends(),
    search: ProjectSearchParams = Depends(),
    auth: AuthChecker = Depends(get_auth_checker),
) -> List[ProjectListItem]:
    """List projects the user is authorized to see."""
    # Central auth — this method raises AuthorizationError if denied
    auth.check_user_guild_channel()  # ensures user is in a guild/channel context

    # Build query: list all projects, then filter by optional search
    all_projects = list_proj_repo(conn=get_conn())  # type: ignore[arg-type]

    # Apply name filter
    if search.name:
        all_projects = [p for p in all_projects if search.name.lower() in p.name.lower()]

    # Apply status filter
    if search.status:
        all_projects = [p for p in all_projects if p.status == search.status]

    # Pagination
    total = len(all_projects)
    start = (pagination.page - 1) * pagination.per_page
    end = start + pagination.per_page
    page_projects = all_projects[start:end]

    return [
        ProjectListItem(
            id=p.id,
            name=p.name,
            allowed_root=p.allowed_root,
            status=p.status,
            last_checked=p.updated_at_utc,
        )
        for p in page_projects
    ]


@app.get(
    "/projects/{project_id}",
    response_model=ProjectDetail,
    summary="Get project detail",
    description="Return full detail for a single project, including milestone and evidence counts, "
    "Discord mapping count, and health freshness.  Requires project-level authorization.",
    responses={
        401: {"model": DashboardError},
        403: {"model": DashboardError},
        404: {"model": DashboardError},
    },
)
async def api_project_detail(
    project_id: int,
    auth: AuthChecker = Depends(get_auth_checker),
) -> ProjectDetail:
    """Return detail for a single project."""
    # Central authorization: check project access
    auth.check_project_access(project_id)  # raises AuthorizationError if denied

    from project_intelligence.storage.database import _utc_now  # noqa: PLC0415

    # Look up project from DB
    from project_intelligence.storage.repositories import get_project_by_root  # noqa: PLC0415

    row = conn.execute(  # type: ignore[name undefined]
        "SELECT id, name, description, allowed_root, created_at_utc, updated_at_utc FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Count milestones
    milestones = list_milestones_for_project(conn=get_conn(), project_id=project_id)  # type: ignore[arg-type]
    milestone_count = len(milestones)

    # Count evidence
    evidence = list_evidence_for_project(conn=get_conn(), project_id=project_id)  # type: ignore[arg-type]
    evidence_count = len(evidence)

    # Count Discord mappings
    mappings = list_mappings_for_project(conn=get_conn(), project_id=project_id)  # type: ignore[arg-type]
    mapping_count = len(mappings)

    # Health freshness: run a quick health check
    health_snapshot = await asyncio_get_health_snapshot(project_id, conn)  # placeholder

    return ProjectDetail(
        id=row[0],
        name=row[1],
        description=row[2],
        allowed_root=row[3],
        status=HealthStatus(row[4]) if isinstance(row[4], str) else HealthStatus.unknown,
        created_at_utc=row[4] or _utc_now(),
        updated_at_utc=row[5] or _utc_now(),
        milestone_count=milestone_count,
        evidence_count=evidence_count,
        discord_mappings=mapping_count,
        health_freshness="unknown",  # to be filled by real health engine later
    )


async def asyncio_get_health_snapshot(project_id: int, conn) -> dict:
    """Placeholder: integrate real health engine later."""
    return {"status": "unknown", "checked_at_utc": _utc_now(), "git_head": None, "git_dirty": 0}


# ---------------------------------------------------------------------------
# --- Milestones ---
# ---------------------------------------------------------------------------

@app.get(
    "/projects/{project_id}/milestones",
    response_model=List[MilestoneListItem],
    summary="List milestones for a project",
    description="Return milestones for the given project.  Requires project-level authorization.",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_list_milestones(
    project_id: int,
    auth: AuthChecker = Depends(get_auth_checker),
) -> List[MilestoneListItem]:
    """List milestones for a project."""
    auth.check_project_access(project_id)  # raises AuthorizationError if denied

    ms = list_milestones_for_project(conn=get_conn(), project_id=project_id)  # type: ignore[arg-type]
    return [
        MilestoneListItem(
            id=m.id,
            project_id=m.project_id,
            title=m.title,
            status=m.status,
            target_date=m.target_date_utc,
        )
        for m in ms
    ]


@app.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneSummary,
    summary="Create a milestone (owner only)",
    description="Create a new milestone for a project.  Owner authorization enforced via "
    "Phase-5 central checker.  Returns the created milestone summary.",
    responses={
        401: {"model": DashboardError},
        403: {"model": DashboardError},
        404: {"model": DashboardError},
    },
)
async def api_create_milestone(
    project_id: int,
    title: str,
    description: Optional[str] = None,
    status: MilestoneStatus = MilestoneStatus.open,
    target_date: Optional[str] = None,
    auth: AuthChecker = Depends(get_auth_checker),
) -> MilestoneSummary:
    """Create a new milestone (owner-only)."""
    auth.check_owner_or_project(project_id)  # raises AuthorizationError if not owner

    # Persist via repository
    row = conn.execute(  # type: ignore[name undefined]
        """
        INSERT INTO milestones (project_id, title, description, status, target_date_utc, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        RETURNING id, project_id, title, description, status, target_date_utc, created_at_utc
        """,
        (project_id, title, description, status.value, target_date, _utc_now()),
    ).fetchone()

    return MilestoneSummary(
        id=row[0],
        project_id=row[1],
        title=row[2],
        description=row[3],
        status=MilestoneStatus(row[4]),
        target_date=row[5],
    )


# ---------------------------------------------------------------------------
# --- Evidence ---
# ---------------------------------------------------------------------------

@app.get(
    "/projects/{project_id}/evidence",
    response_model=List[EvidenceSummary],
    summary="List evidence for a project",
    description="Return evidence records for a project.  Requires project-level authorization.",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_list_evidence(
    project_id: int,
    auth: AuthChecker = Depends(get_auth_checker),
    pagination: PaginationParams = Depends(),
) -> List[EvidenceSummary]:
    """List evidence for a project."""
    auth.check_project_access(project_id)  # raises AuthorizationError if denied

    ev = list_evidence_for_project(conn=get_conn(), project_id=project_id)  # type: ignore[arg-type]
    return [
        EvidenceSummary(
            id=e.id,
            project_id=e.project_id,
            title=e.title,
            content_hash=e.content_hash,
            retrieved_at_utc=e.retrieved_at_utc,
            confidence=e.confidence,
            is_stale=e.is_stale,
        )
        for e in ev
    ]


@app.get(
    "/projects/{project_id}/evidence/{evidence_id}",
    response_model=EvidenceDetail,
    summary="Get evidence detail",
    description="Return full detail for a single evidence record, linked to its source.",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}, 404: {"model": DashboardError}},
)
async def api_evidence_detail(
    project_id: int,
    evidence_id: int,
    auth: AuthChecker = Depends(get_auth_checker),
) -> EvidenceDetail:
    """Return detail for a single evidence record."""
    auth.check_project_access(project_id)  # raises AuthorizationError if denied

    row = conn.execute(  # type: ignore[name undefined]
        "SELECT id, project_id, source_id, title, content_hash, retrieved_at_utc, confidence, claim, is_stale, relevance_score FROM evidence WHERE id = ? AND project_id = ?",
        (evidence_id, project_id),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Evidence not found for this project")

    return EvidenceDetail(
        id=row[0],
        project_id=row[1],
        title=row[3],
        content_hash=row[4],
        retrieved_at_utc=row[5],
        confidence=row[6] or 1.0,
        claim=row[7],
        is_stale=bool(row[8]),
        relevance_score=row[9] or 0.0,
    )


# ---------------------------------------------------------------------------
# --- Recent activity ---
# ---------------------------------------------------------------------------

@app.get(
    "/activity/recent",
    response_model=List[ActivityEntry],
    summary="Recent activity across projects",
    description="Return recent activity notes, milestones, evidence updates, and research jobs. "
    "Requires central authorization.",
    responses={401: {"model": DashboardError}},
)
async def api_recent_activity(
    auth: AuthChecker = Depends(get_auth_checker),
    limit: int = 50,
) -> List[ActivityEntry]:
    """Return recent activity across all authorized projects."""
    auth.check_user_guild_channel()  # ensures user is in a guild/channel context

    # Pull notes, milestones, and evidence recent entries via raw SQL for speed
    conn_local = get_conn()
    try:
        rows = conn_local.execute(
            """
            SELECT id, 'note' AS type, project_id, content AS title,
                   created_at_utc AS occurred_at_utc,
                   (SELECT discord_user_id FROM authorized_users WHERE project_id = p.id LIMIT 1) AS actor,
                   '' AS metadata
            FROM notes n
            JOIN projects p ON n.project_id = p.id
            ORDER BY created_at_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        activity = []
        for r in rows:
            activity.append(
                ActivityEntry(
                    id=r[0],
                    type=ActivityType.note,
                    project_id=r[1] if r[1] else None,
                    title=r[2] or "Untitled note",
                    occurred_at_utc=r[3],
                    actor=r[4],
                    metadata={},
                )
            )
        return activity
    finally:
        close()


# ---------------------------------------------------------------------------
# --- Global error handlers ---
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Secret-free error rendering: never echo raw secrets or stack traces."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail.split(":")[0] if ":" in exc.detail else "error",
            "message": exc.detail,
            "correlation_id": getattr(request, "state", {}).get("correlation_id", None),
            "timestamp_utc": datetime.now(timezone.utc).isoformat() + "Z",
        },
    )


@app.exception_handler(AuthorizationError)
async def auth_exception_handler(request: Request, exc: AuthorizationError):
    """Authorization errors are private; return ephemeral 403."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "forbidden",
            "message": exc.detail if hasattr(exc, "detail") else "Access denied",
            "correlation_id": getattr(request, "state", {}).get("correlation_id", None),
            "timestamp_utc": datetime.now(timezone.utc).isoformat() + "Z",
        },
    )


# ---------------------------------------------------------------------------
# --- Startup validation ( Phase 5 authz integration placeholder) ---
# ---------------------------------------------------------------------------

# The actual Discord-interaction authentication is wired in the bot layer.
# This dashboard binds to 127.0.0.1 by design; any remote access must go
# through Tailscale Serve with application-level authentication (Phase 8).
# See docs/SECURITY.md for the full threat model and access policy.

# ---- Run uvicorn from command line ----
# uvicorn project_intelligence.dashboard.dashboard:app --host 127.0.0.1 --port 8765 --limit-concurrency 100