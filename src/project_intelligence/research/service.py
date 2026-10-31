"""Research orchestration across local knowledge and the public web.

A research job is persisted before any work starts, so failures are visible in
the dashboard instead of disappearing with an exception.  Local research never
leaves the machine.  Web research is opt-in per job and only runs when a
search provider and API key are configured.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from project_intelligence.config import Settings, load_settings
from project_intelligence.research.local_research import (
    LocalFinding,
    build_local_report,
    research_local,
)
from project_intelligence.research.web_research import (
    ResearchError,
    ResearchNotConfigured,
    WebFinding,
    research_web,
)

# Optional YouTube video research (Phase 15+ extension)
try:
    from project_intelligence.research.youtube import (
        YouTubeFetcher,
        research_youtube,
        youtube_to_web_finding,
    )

    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False
from project_intelligence.storage import repositories as repo
from project_intelligence.storage.database import get_conn

logger = logging.getLogger(__name__)

VALID_SCOPES = ("local", "web", "both", "youtube")


@dataclass
class ResearchResult:
    job_id: int
    status: str
    scope: str
    provider: str | None
    report: str
    source_count: int
    local_count: int = 0
    web_count: int = 0
    error: str | None = None


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strip_heading(report: str | list[str], heading: str) -> str:
    text = "\n".join(report) if isinstance(report, list) else (report if isinstance(report, str) else "")
    lines = text.strip().splitlines()
    if lines and lines[0].strip() == heading:
        lines = lines[1:]
    return "\n".join(lines).strip()


def _combine_reports(
    question: str,
    scope: str,
    provider: str | None,
    local_report: str | None,
    web_report: str | None,
    youtube_report: str | None = None,
    notes: list[str] | None = None,
) -> str:
    lines = [
        "# Research report",
        "",
        f"**Question:** {question}",
        f"**Scope:** {scope}",
        f"**Web provider:** {provider or 'not configured'}",
        "",
    ]
    # If youtube_report passed as a list (notes), treat as notes; skip YouTube section
    if isinstance(youtube_report, list):
        notes = youtube_report if notes is None else notes + youtube_report
        youtube_report = None

    if notes:
        lines.extend(f"> {note}" for note in notes)
        lines.append("")

    if local_report:
        lines.append("## Local knowledge")
        lines.append("")
        lines.append(_strip_heading(local_report, "# Local research"))
        lines.append("")
    if web_report:
        lines.append("## Web sources")
        lines.append("")
        lines.append(_strip_heading(web_report, "# Web research"))
        lines.append("")
    if youtube_report:
        lines.append("## YouTube videos")
        lines.append("")
        lines.append(_strip_heading(youtube_report, "# YouTube research"))
        lines.append("")
    if not local_report and not web_report and not youtube_report:
        lines.append("No sources were found.")
    return "\n".join(lines).rstrip() + "\n"


def _store_local_sources(job_id: int, findings: list[LocalFinding]) -> None:
    conn = get_conn()
    for index, finding in enumerate(findings, start=1):
        repo.upsert_research_source(
            conn,
            job_id,
            f"[local] {index}. {finding.title} ({finding.source_ref})",
            None,
            finding.source_type,
            _content_hash(f"{finding.source_ref}|{finding.snippet}"),
            snippet=finding.snippet,
            relevance_score=finding.score,
            source_ref=finding.source_ref,
        )


def _store_web_sources(job_id: int, findings: list[WebFinding]) -> None:
    conn = get_conn()
    for index, finding in enumerate(findings, start=1):
        repo.upsert_research_source(
            conn,
            job_id,
            f"[web] {index}. {finding.title}"[:300],
            finding.url,
            "web",
            finding.content_hash or _content_hash(finding.url),
            snippet=finding.snippet,
            relevance_score=finding.score,
            source_ref=finding.url,
        )


def run_research(
    question: str,
    *,
    project_id: int | None = None,
    user_id: int | None = None,
    scope: str = "both",
    settings: Settings | None = None,
) -> ResearchResult:
    """Run a persisted local and/or web research job."""
    settings = settings or load_settings()
    normalized_question = " ".join(question.split()).strip()
    if not normalized_question:
        raise ValueError("Research question cannot be empty")
    if len(normalized_question) > 1000:
        raise ValueError("Research question must be 1000 characters or fewer")
    normalized_scope = scope.strip().lower()
    if normalized_scope not in VALID_SCOPES:
        raise ValueError(f"Research scope must be one of: {', '.join(VALID_SCOPES)}")

    conn = get_conn()
    if project_id is not None and repo.get_project_by_id(conn, project_id) is None:
        raise ValueError(f"Project {project_id} was not found")

    provider_name = (
        (settings.research_provider or "").strip().lower() or None
        if normalized_scope in {"web", "both"}
        else None
    )
    job = repo.upsert_research_job(
        conn,
        project_id,
        user_id,
        normalized_question,
        scope=normalized_scope,
        provider=provider_name,
    )
    conn.commit()
    logger.info(
        "research job %s started (scope=%s, provider=%s, project=%s, question_chars=%s)",
        job.id,
        normalized_scope,
        provider_name or "none",
        project_id,
        len(normalized_question),
    )

    local_findings: list[LocalFinding] = []
    web_findings: list[WebFinding] = []
    local_report: str | None = None
    web_report: str | None = None
    notes: list[str] = []

    try:
        youtube_findings: list[WebFinding] = []
        youtube_report: str | None = None

        if normalized_scope == "youtube":
            try:
                from project_intelligence.research.youtube import (
                    is_youtube_url,
                    research_youtube,
                )

                youtube_urls = []
                for line in normalized_question.splitlines():
                    words = line.split()
                    for word in words:
                        url = word.strip()
                        if is_youtube_url(url):
                            youtube_urls.append(url)

                # Also check for URLs embedded anywhere in the question
                import re
                url_matches = re.findall(
                    r"https?://(?:www\.)?youtube\.com/[\w?/=%&#_-]+|https?://youtu\.be/[\w?/=%&#_-]+",
                    normalized_question,
                )
                for url in url_matches:
                    if is_youtube_url(url) and url not in youtube_urls:
                        youtube_urls.append(url)

                if not youtube_urls:
                    youtube_urls = [normalized_question]

                youtube_findings, youtube_report = research_youtube(
                    normalized_question,
                    youtube_urls,
                    settings=settings,
                )
            except Exception as exc:
                notes.append(f"YouTube research failed: {type(exc).__name__}")
                youtube_findings = []
                youtube_report = None

        if normalized_scope in {"local", "both"}:
            local_findings, local_report = research_local(
                normalized_question,
                project_id=project_id,
                settings=settings,
            )

        if normalized_scope in {"web", "both"}:
            try:
                web_findings, web_report = research_web(
                    normalized_question,
                    settings=settings,
                )
            except ResearchNotConfigured as exc:
                if normalized_scope == "web":
                    message = str(exc)
                    repo.complete_research_job(
                        conn,
                        job.id,
                        status="failed",
                        result_summary=message,
                        error_text=message,
                    )
                    conn.commit()
                    return ResearchResult(
                        job_id=job.id,
                        status="failed",
                        scope=normalized_scope,
                        provider=provider_name,
                        report="",
                        source_count=0,
                        error=message,
                    )
                notes.append(f"Web research skipped: {exc}")
            except ResearchError as exc:
                if normalized_scope == "web":
                    message = str(exc)
                    repo.complete_research_job(
                        conn,
                        job.id,
                        status="failed",
                        result_summary=message,
                        error_text=message,
                    )
                    conn.commit()
                    return ResearchResult(
                        job_id=job.id,
                        status="failed",
                        scope=normalized_scope,
                        provider=provider_name,
                        report="",
                        source_count=0,
                        error=message,
                    )
                notes.append(f"Web research failed: {exc}")

        _store_local_sources(job.id, local_findings)
        _store_web_sources(job.id, web_findings)
        if YOUTUBE_AVAILABLE and normalized_scope == "youtube":

            for finding in youtube_findings:
                repo.upsert_research_source(
                    conn,
                    job.id,
                    f"[youtube] {finding.title}"[:300],
                    finding.url,
                    "youtube",
                    finding.content_hash or _content_hash(finding.url),
                    snippet=finding.snippet,
                    relevance_score=finding.score,
                    source_ref=finding.url,
                )
        report = _combine_reports(
            normalized_question,
            normalized_scope,
            provider_name,
            local_report,
            web_report,
            youtube_report,
            notes,
        )
        source_count = len(local_findings) + len(web_findings) + len(youtube_findings)
        repo.upsert_research_report(
            conn,
            job.id,
            report,
            citation_count=source_count,
        )
        summary = (
            f"{source_count} source{'' if source_count == 1 else 's'} "
            f"({len(local_findings)} local, {len(web_findings)} web)"
        )
        repo.complete_research_job(
            conn,
            job.id,
            status="completed",
            result_summary=summary,
        )
        conn.commit()
        logger.info("research job %s completed with %s sources", job.id, source_count)
        return ResearchResult(
            job_id=job.id,
            status="completed",
            scope=normalized_scope,
            provider=provider_name,
            report=report,
            source_count=source_count,
            local_count=len(local_findings),
            web_count=len(web_findings),
        )
    except Exception as exc:
        conn.rollback()
        message = f"Research failed: {type(exc).__name__}"
        try:
            repo.complete_research_job(
                conn,
                job.id,
                status="failed",
                result_summary=message,
                error_text=message,
            )
            conn.commit()
        except Exception:  # pragma: no cover - database failure while recording failure
            conn.rollback()
        logger.exception("research job %s failed", job.id)
        raise ResearchError(message) from None


def research_history(project_id: int | None = None, *, limit: int = 20) -> list[repo.ResearchJob]:
    """Return recent research jobs, optionally scoped to one project."""
    conn = get_conn()
    if project_id is None:
        return repo.list_recent_research_jobs(conn, limit=limit)
    return repo.list_research_jobs_for_project(conn, project_id)[:limit]


__all__ = [
    "VALID_SCOPES",
    "ResearchResult",
    "build_local_report",
    "research_history",
    "run_research",
]
