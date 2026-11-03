"""Dashboard API and mobile UI for Discord Project Intelligence.

FastAPI application providing:
- Application health, project list/detail, milestones, evidence, recent activity
- Owner-session authentication (Phase 8) plus centralized authorization (Phase 5)
- A minimal, mobile-first HTML interface served at ``/`` for iPhone browsers
- Loopback bind 127.0.0.1 by default; remote access only via Tailscale Serve
- Safe error handling without stack traces or secret leakage
- Pagination and bounded response sizes

Authentication model
--------------------
- ``GET``/``HEAD`` requests may authenticate with the signed owner-session
  cookie issued by ``POST /auth/session`` (the owner secret is the one-time
  credential; the cookie is an HttpOnly, SameSite=Strict HMAC token).
- State-changing requests never accept cookie authentication, so no
  state-changing endpoint is reachable via CSRF.
- Discord interaction context authentication is wired by the bot layer in a
  later integration; browser access uses the owner session.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from project_intelligence.config import Settings, load_settings
from project_intelligence.dashboard import session_auth
from project_intelligence.dashboard.schemas import (
    ActivityEntry,
    ActivityType,
    CatalogSummary,
    DashboardError,
    DashboardHealth,
    EvidenceDetail,
    EvidenceSummary,
    HealthStatus,
    MilestoneListItem,
    MilestoneStatus,
    MilestoneSummary,
    PaginationParams,
    ProjectDetail,
    ProjectListItem,
    ProjectSearchParams,
    ResearchJobDetail,
    ResearchJobSummary,
    ResearchSourceSummary,
    WorkItemSummary,
)
from project_intelligence.security import (
    AuthContext,
    AuthError,
    AuthorizationError,
    make_checker,
)
from project_intelligence.security.authorization import AuthorizationChecker
from project_intelligence.storage import repositories as repo
from project_intelligence.storage.database import close as close_database
from project_intelligence.storage.database import get_conn

logger = logging.getLogger(__name__)

_STARTED_AT = time.monotonic()
_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Sign-in throttling: per-client sliding window, in-memory (single process).
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 60.0


# ---------------------------------------------------------------------------
# Lifespan / startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: validate configuration and open the database (migrates)."""
    settings = load_settings()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    get_conn()  # creates the database and applies pending migrations
    logger.info("dashboard started (env=%s)", settings.app_env)
    try:
        yield
    finally:
        close_database()


app = FastAPI(
    title="Discord Project Intelligence - Dashboard API",
    description="Private, read-only project-intelligence dashboard (loopback-bind only).",
    version="0.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_settings() -> Settings:
    """Return loaded (validated) application settings."""
    return load_settings()


def get_auth_context(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Authenticate the request.

    Read-only requests accept the owner-session cookie.  Everything else is
    rejected here; Discord interaction authentication is provided by the bot
    layer and will be added when interactions are wired to the dashboard.
    """
    if request.method in ("GET", "HEAD"):
        token = request.cookies.get(session_auth.SESSION_COOKIE_NAME)
        if session_auth.verify_session_token(token, settings):
            return session_auth.owner_auth_context(settings)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required - sign in to the dashboard",
    )


def get_auth_checker(
    settings: Settings = Depends(get_settings),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> AuthorizationChecker:
    """Return a per-request AuthorizationChecker instance."""
    return make_checker(auth_ctx, settings)


# ---------------------------------------------------------------------------
# Session request/response models
# ---------------------------------------------------------------------------


class SessionLoginRequest(BaseModel):
    """One-time presentation of the owner secret."""

    token: str = Field(min_length=1, max_length=512)


class SessionStatus(BaseModel):
    """Current session state."""

    authenticated: bool
    expires_at_utc: str | None = None


class MilestoneCreate(BaseModel):
    """Payload for creating or updating a milestone."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: MilestoneStatus = MilestoneStatus.open
    target_date: str | None = Field(default=None, max_length=40)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login_allowed(client: str) -> bool:
    now = time.monotonic()
    attempts = [t for t in _LOGIN_ATTEMPTS.get(client, []) if now - t < _LOGIN_WINDOW_SECONDS]
    if attempts:
        _LOGIN_ATTEMPTS[client] = attempts
    else:
        _LOGIN_ATTEMPTS.pop(client, None)
    return len(attempts) < _LOGIN_MAX_ATTEMPTS


def _record_failed_login(client: str) -> None:
    _LOGIN_ATTEMPTS.setdefault(client, []).append(time.monotonic())


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _parse_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _health_freshness(checked_at_utc: str) -> str:
    parsed = _parse_utc(checked_at_utc)
    if parsed is None:
        return "unknown"
    age = (datetime.now(UTC) - parsed).total_seconds()
    if age <= 24 * 3600:
        return "fresh"
    if age <= 7 * 24 * 3600:
        return "stale"
    return "unknown"


def _health_status(value: str | None) -> HealthStatus:
    try:
        return HealthStatus(value) if value is not None else HealthStatus.unknown
    except ValueError:
        return HealthStatus.unknown


def _milestone_status(value: str) -> MilestoneStatus:
    try:
        return MilestoneStatus(value)
    except ValueError:
        return MilestoneStatus.open


def _clamp_unit(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, number))


def _tech_stack(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()][:20]


def _work_item_summary(item: repo.WorkItem) -> WorkItemSummary:
    return WorkItemSummary(
        id=item.id,
        project_id=item.project_id,
        work_type=item.work_type,
        title=item.title,
        body=item.body,
        status=item.status,
        source=item.source,
        occurred_at_utc=item.occurred_at_utc,
    )


def _research_summary(
    job: repo.ResearchJob,
    *,
    project_name: str | None = None,
    source_count: int = 0,
) -> ResearchJobSummary:
    return ResearchJobSummary(
        id=job.id,
        project_id=job.project_id,
        project_name=project_name,
        question=job.question,
        status=job.status,
        scope=job.scope,
        provider=job.provider,
        started_at_utc=job.started_at_utc,
        completed_at_utc=job.completed_at_utc,
        result_summary=job.result_summary,
        source_count=source_count,
        error=job.error_text,
    )


def _error_response(request: Request, status_code: int, error: str, message: str) -> JSONResponse:
    payload = DashboardError(
        error=error,
        message=message,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Exception handlers - never leak internals
# ---------------------------------------------------------------------------


@app.exception_handler(AuthorizationError)
async def _handle_authorization_error(request: Request, exc: AuthorizationError) -> JSONResponse:
    return _error_response(request, status.HTTP_403_FORBIDDEN, "forbidden", exc.message)


@app.exception_handler(AuthError)
async def _handle_auth_error(request: Request, exc: AuthError) -> JSONResponse:
    return _error_response(request, status.HTTP_401_UNAUTHORIZED, "unauthorized", exc.message)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def ui_index() -> FileResponse:
    """Serve the mobile-first dashboard UI."""
    index = _STATIC_DIR / "index.html"
    if not index.is_file():  # pragma: no cover - packaging failure
        raise HTTPException(status_code=404, detail="Dashboard UI is not installed")
    return FileResponse(index, media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@app.post(
    "/auth/session",
    response_model=SessionStatus,
    summary="Sign in with the owner secret",
    description="Exchange the owner secret (dashboard session secret file) for a signed, "
    "HttpOnly session cookie.  Rate limited per client.",
    responses={401: {"model": DashboardError}, 429: {"model": DashboardError}},
)
async def api_login(
    payload: SessionLoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> SessionStatus:
    client = _client_host(request)
    if not _login_allowed(client):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts; try again in a minute",
        )

    if not session_auth.verify_owner_secret(payload.token.strip(), settings):
        _record_failed_login(client)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid dashboard token")

    token, expires = session_auth.issue_session_token(settings)
    response.set_cookie(
        session_auth.SESSION_COOKIE_NAME,
        token,
        **session_auth.get_cookie_security_settings(settings),
    )
    return SessionStatus(
        authenticated=True,
        expires_at_utc=datetime.fromtimestamp(expires, UTC).isoformat(),
    )


@app.get(
    "/auth/session",
    response_model=SessionStatus,
    summary="Report current session state",
)
async def api_session_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SessionStatus:
    token = request.cookies.get(session_auth.SESSION_COOKIE_NAME)
    return SessionStatus(authenticated=session_auth.verify_session_token(token, settings))


@app.post(
    "/auth/logout",
    response_model=SessionStatus,
    summary="Clear the session cookie",
)
async def api_logout(response: Response) -> SessionStatus:
    response.delete_cookie(session_auth.SESSION_COOKIE_NAME, path="/")
    return SessionStatus(authenticated=False)


# ---------------------------------------------------------------------------
# /health (global application status; intentionally unauthenticated)
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=DashboardHealth,
    summary="Application and integration health status",
    description="Return overall application status including environment, dashboard bind address, "
    "and whether Ollama/research are configured.  Always bound to loopback.",
)
async def api_health(settings: Settings = Depends(get_settings)) -> DashboardHealth:
    """Global application health - no project or guild scoping required."""
    database_healthy = True
    try:
        get_conn().execute("SELECT 1").fetchone()
    except Exception:  # pragma: no cover - catastrophic DB failure
        database_healthy = False

    new_modules = {"voice": False, "image_gen": False, "vision": False}
    try:
        from project_intelligence.discord.image_gen import IMAGE_GEN_AVAILABLE
        from project_intelligence.discord.vision import VISION_AVAILABLE
        from project_intelligence.discord.voice import VOICE_SPEECH_AVAILABLE

        new_modules = {
            "voice": VOICE_SPEECH_AVAILABLE,
            "image_gen": IMAGE_GEN_AVAILABLE,
            "vision": VISION_AVAILABLE,
        }
    except Exception as exc:  # pragma: no cover - import failure
        logger.debug("import failed: %s", exc)

    return DashboardHealth(
        app_env=settings.app_env,
        app_log_level=settings.app_log_level,
        database_healthy=database_healthy,
        dashboard_bound_host=settings.dashboard_bind_host,
        dashboard_bound_port=settings.dashboard_bind_port,
        ollama_configured=settings.ollama_model is not None,
        research_configured=(
            settings.research_provider in {"tavily", "brave"} and settings.research_api_key is not None
        ),
        uptime_seconds=round(time.monotonic() - _STARTED_AT, 3),
        new_modules=new_modules,
    )


@app.get("/health/modules", response_model=dict[str, bool])
async def api_health_modules(settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    """Health status for Phase 27+ feature modules."""
    modules = {"voice": False, "image_gen": False, "vision": False}
    try:
        from project_intelligence.discord.image_gen import IMAGE_GEN_AVAILABLE
        from project_intelligence.discord.vision import VISION_AVAILABLE
        from project_intelligence.discord.voice import VOICE_SPEECH_AVAILABLE

        modules = {
            "voice": VOICE_SPEECH_AVAILABLE,
            "image_gen": IMAGE_GEN_AVAILABLE,
            "vision": VISION_AVAILABLE,
        }
    except Exception as exc:  # pragma: no cover - import failure
        logger.debug("module import failed: %s", exc)
    return modules


@app.get(
    "/projects",
    response_model=list[ProjectListItem],
    summary="List authorized projects",
    description="Return a paginated list of projects the authenticated user is authorized to view.",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_project_list(
    pagination: PaginationParams = Depends(),
    search: ProjectSearchParams = Depends(),
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> list[ProjectListItem]:
    """List projects the user is authorized to see."""
    auth.check_user_guild_channel()

    conn = get_conn()
    projects = repo.list_projects(conn)
    if search.name:
        needle = search.name.lower()
        projects = [p for p in projects if needle in p.name.lower()]

    items: list[ProjectListItem] = []
    for project in projects:
        snapshot = repo.get_latest_health_snapshot(conn, project.id)
        items.append(
            ProjectListItem(
                id=project.id,
                name=project.name,
                description=project.description,
                allowed_root=project.allowed_root,
                status=_health_status(snapshot[0] if snapshot else None),
                last_checked=snapshot[1] if snapshot else (project.last_activity_utc or project.updated_at_utc),
                catalog_status=project.catalog_status,
                category=project.category,
                priority=project.priority,
                tech_stack=_tech_stack(project.tech_stack_json),
                source=project.source,
                monitored=bool(project.monitored),
                last_activity_utc=project.last_activity_utc,
                work_item_count=repo.count_work_items(conn, project.id),
                repo_url=project.repo_url,
            )
        )

    if search.status:
        items = [item for item in items if item.status == search.status]

    start = (pagination.page - 1) * pagination.per_page
    return items[start : start + pagination.per_page]


@app.get(
    "/projects/{project_id}",
    response_model=ProjectDetail,
    summary="Get project detail",
    description="Return full detail for a single project, including milestone and evidence counts, "
    "Discord mapping count, and health freshness.",
    responses={
        401: {"model": DashboardError},
        403: {"model": DashboardError},
        404: {"model": DashboardError},
    },
)
async def api_project_detail(
    project_id: int,
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> ProjectDetail:
    """Return detail for a single project."""
    auth.check_project_access(project_id)

    conn = get_conn()
    project = repo.get_project_by_id(conn, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    snapshot = repo.get_latest_health_snapshot(conn, project_id)
    work_items = repo.list_work_items_for_project(conn, project_id, limit=5)
    research_jobs = repo.list_research_jobs_for_project(conn, project_id)
    return ProjectDetail(
        id=project.id,
        name=project.name,
        description=project.description,
        allowed_root=project.allowed_root,
        status=_health_status(snapshot[0] if snapshot else None),
        created_at_utc=project.created_at_utc,
        updated_at_utc=project.updated_at_utc,
        milestone_count=len(repo.list_milestones_for_project(conn, project_id)),
        evidence_count=len(repo.list_evidence_for_project(conn, project_id)),
        discord_mappings=len(repo.list_mappings_for_project(conn, project_id)),
        health_freshness=_health_freshness(snapshot[1]) if snapshot else "unknown",
        catalog_status=project.catalog_status,
        category=project.category,
        priority=project.priority,
        tech_stack=_tech_stack(project.tech_stack_json),
        repo_url=project.repo_url,
        local_path=project.local_path,
        source=project.source,
        monitored=bool(project.monitored),
        last_activity_utc=project.last_activity_utc,
        work_item_count=repo.count_work_items(conn, project_id),
        research_count=len(research_jobs),
        recent_work=[_work_item_summary(item) for item in work_items],
        recent_research=[
            _research_summary(
                job,
                project_name=project.name,
                source_count=repo.count_research_sources(conn, job.id),
            )
            for job in research_jobs[:5]
        ],
    )


# ---------------------------------------------------------------------------
# --- Milestones ---
# ---------------------------------------------------------------------------


@app.get(
    "/projects/{project_id}/milestones",
    response_model=list[MilestoneListItem],
    summary="List milestones for a project",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_list_milestones(
    project_id: int,
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> list[MilestoneListItem]:
    auth.check_project_access(project_id)
    milestones = repo.list_milestones_for_project(get_conn(), project_id)
    return [
        MilestoneListItem(
            id=m.id,
            project_id=m.project_id,
            title=m.title,
            status=_milestone_status(m.status),
            target_date=m.target_date_utc,
        )
        for m in milestones
    ]


@app.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a milestone",
    description="State-changing endpoint.  Cookie sessions are not accepted for writes; "
    "this requires Discord interaction context.",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_upsert_milestone(
    project_id: int,
    payload: MilestoneCreate,
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> MilestoneSummary:
    auth.check_project_access(project_id)
    conn = get_conn()
    milestone = repo.upsert_milestone(
        conn,
        project_id=project_id,
        title=payload.title,
        description=payload.description,
        status=payload.status.value,
        target_date_utc=payload.target_date,
    )
    conn.commit()
    return MilestoneSummary(
        id=milestone.id,
        title=milestone.title,
        description=milestone.description,
        status=_milestone_status(milestone.status),
        target_date=milestone.target_date_utc,
        created_at=milestone.created_at_utc,
    )


# ---------------------------------------------------------------------------
# --- Evidence ---
# ---------------------------------------------------------------------------


@app.get(
    "/projects/{project_id}/evidence",
    response_model=list[EvidenceSummary],
    summary="List evidence for a project",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_list_evidence(
    project_id: int,
    auth: AuthorizationChecker = Depends(get_auth_checker),
    pagination: PaginationParams = Depends(),
) -> list[EvidenceSummary]:
    auth.check_project_access(project_id)
    evidence = repo.list_evidence_for_project(get_conn(), project_id)
    start = (pagination.page - 1) * pagination.per_page
    return [
        EvidenceSummary(
            id=e.id,
            title=e.title,
            content_hash=e.content_hash,
            retrieved_at_utc=e.retrieved_at_utc,
            confidence=_clamp_unit(e.confidence),
            is_stale=bool(e.is_stale),
        )
        for e in evidence[start : start + pagination.per_page]
    ]


@app.get(
    "/projects/{project_id}/evidence/{evidence_id}",
    response_model=EvidenceDetail,
    summary="Get one evidence record",
    responses={
        401: {"model": DashboardError},
        403: {"model": DashboardError},
        404: {"model": DashboardError},
    },
)
async def api_evidence_detail(
    project_id: int,
    evidence_id: int,
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> EvidenceDetail:
    auth.check_project_access(project_id)
    evidence = repo.get_evidence(get_conn(), project_id, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return EvidenceDetail(
        id=evidence.id,
        project_id=evidence.project_id,
        title=evidence.title,
        content_hash=evidence.content_hash,
        retrieved_at_utc=evidence.retrieved_at_utc,
        confidence=_clamp_unit(evidence.confidence),
        claim=evidence.claim,
        is_stale=bool(evidence.is_stale),
        relevance_score=_clamp_unit(evidence.relevance_score),
    )


# ---------------------------------------------------------------------------
# --- Research ---
# ---------------------------------------------------------------------------


@app.get(
    "/research",
    response_model=list[ResearchJobSummary],
    summary="List recent research jobs",
    description="Return recent local/web research jobs, optionally scoped to one project.",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_research_list(
    project_id: int | None = None,
    pagination: PaginationParams = Depends(),
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> list[ResearchJobSummary]:
    """List research jobs newest first."""
    if project_id is not None:
        auth.check_project_access(project_id)
    else:
        auth.check_user_guild_channel()

    conn = get_conn()
    if project_id is not None:
        jobs = repo.list_research_jobs_for_project(conn, project_id)
    else:
        jobs = repo.list_recent_research_jobs(conn, limit=100)
    names = {project.id: project.name for project in repo.list_projects(conn)}
    start = (pagination.page - 1) * pagination.per_page
    return [
        _research_summary(
            job,
            project_name=names.get(job.project_id) if job.project_id is not None else None,
            source_count=repo.count_research_sources(conn, job.id),
        )
        for job in jobs[start : start + pagination.per_page]
    ]


@app.get(
    "/research/{job_id}",
    response_model=ResearchJobDetail,
    summary="Get a research report and its sources",
    responses={
        401: {"model": DashboardError},
        403: {"model": DashboardError},
        404: {"model": DashboardError},
    },
)
async def api_research_detail(
    job_id: int,
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> ResearchJobDetail:
    """Return one persisted research report with citations."""
    auth.check_user_guild_channel()
    conn = get_conn()
    job = repo.get_research_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research job not found")
    if job.project_id is not None:
        auth.check_project_access(job.project_id)

    project = repo.get_project_by_id(conn, job.project_id) if job.project_id is not None else None
    report = repo.get_research_report(conn, job_id)
    sources = repo.list_research_sources(conn, job_id)
    return ResearchJobDetail(
        **_research_summary(
            job,
            project_name=project.name if project is not None else None,
            source_count=len(sources),
        ).model_dump(),
        report_text=report.report_text if report is not None else None,
        report_generated_at_utc=report.generated_at_utc if report is not None else None,
        sources=[
            ResearchSourceSummary(
                id=source.id,
                title=source.title,
                url=source.canonical_url,
                source_type=source.source_type,
                snippet=source.snippet,
                relevance_score=source.relevance_score,
                source_ref=source.source_ref,
                retrieved_at_utc=source.retrieved_at_utc,
            )
            for source in sources
        ],
    )


@app.get(
    "/catalog/summary",
    response_model=CatalogSummary,
    summary="Summarize the imported project catalog",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_catalog_summary(
    auth: AuthorizationChecker = Depends(get_auth_checker),
) -> CatalogSummary:
    """Return counts for the dashboard home and catalog header."""
    auth.check_user_guild_channel()
    conn = get_conn()
    projects = repo.list_projects(conn)
    latest = repo.get_latest_catalog_import(conn)
    return CatalogSummary(
        project_count=len(projects),
        monitored_count=sum(1 for project in projects if project.monitored),
        catalog_count=sum(1 for project in projects if project.source == "catalog"),
        active_count=sum(1 for project in projects if project.catalog_status == "active"),
        work_item_count=repo.count_all_work_items(conn),
        research_job_count=repo.count_research_jobs(conn),
        categories=sorted({project.category for project in projects if project.category}),
        last_import_at_utc=latest.imported_at_utc if latest is not None else None,
    )


# ---------------------------------------------------------------------------
# --- Recent activity ---
# ---------------------------------------------------------------------------


@app.get(
    "/activity/recent",
    response_model=list[ActivityEntry],
    summary="Recent activity across projects",
    description="Return the most recent notes (newest first).",
    responses={401: {"model": DashboardError}, 403: {"model": DashboardError}},
)
async def api_recent_activity(
    auth: AuthorizationChecker = Depends(get_auth_checker),
    pagination: PaginationParams = Depends(),
) -> list[ActivityEntry]:
    auth.check_user_guild_channel()
    rows = (
        get_conn()
        .execute(
            "SELECT id, project_id, content, discord_user_id, created_at_utc "
            "FROM notes ORDER BY created_at_utc DESC, id DESC LIMIT ?",
            (pagination.per_page,),
        )
        .fetchall()
    )
    return [
        ActivityEntry(
            id=row[0],
            type=ActivityType.note,
            project_id=row[1],
            title=(row[2] or "")[:80],
            occurred_at_utc=row[4],
            actor=f"<@{row[3]}>" if row[3] else "system",
        )
        for row in rows
    ]
