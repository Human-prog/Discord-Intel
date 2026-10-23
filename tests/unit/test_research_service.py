"""Persisted research orchestration across local knowledge and the web."""

from __future__ import annotations

import hashlib

import pytest

from project_intelligence.research import service
from project_intelligence.research.service import (
    ResearchResult,
    _combine_reports,
    _content_hash,
    _strip_heading,
    research_history,
    run_research,
)
from project_intelligence.research.web_research import (
    ResearchError,
    WebFinding,
)
from project_intelligence.storage import repositories as repo


def _seed_project(db, name: str = "Alpha research") -> repo.Project:
    project = repo.upsert_project(db, name, "A discord research dashboard", "/srv/alpha")
    repo.upsert_work_item(
        db,
        project.id,
        "commit",
        "Build research dashboard",
        body="discord research and local search",
        source="git",
        external_id="a" * 40,
    )
    repo.upsert_note(db, project.id, 1, "A research note about the dashboard")
    db.commit()
    return project


def _fake_web(monkeypatch, *, error=None, findings=None, report="# Web research\n\nweb body\n"):
    def fake(question, *, settings, provider=None, fetcher=None):
        if error is not None:
            raise error
        return findings or [], report

    monkeypatch.setattr(service, "research_web", fake)


def test_strip_heading_and_combine_reports() -> None:
    assert _strip_heading("# Local research\n\nbody", "# Local research") == "body"
    assert _strip_heading("body\nmore", "# Local research") == "body\nmore"
    assert _combine_reports("q", "local", None, None, None, ["note"]) == (
        "# Research report\n"
        "\n"
        "**Question:** q\n"
        "**Scope:** local\n"
        "**Web provider:** not configured\n"
        "\n"
        "> note\n"
        "\n"
        "No sources were found.\n"
    )
    combined = _combine_reports(
        "q", "both", "tavily", "# Local research\nlocal body", "# Web research\nweb body", []
    )
    assert "## Local knowledge\n\nlocal body" in combined
    assert "## Web sources\n\nweb body" in combined


def test_content_hash_is_stable() -> None:
    assert _content_hash("x") == hashlib.sha256(b"x").hexdigest()


def test_run_research_local_persists_job_report_and_sources(db, app_settings) -> None:
    project = _seed_project(db)
    result = run_research(
        "  discord   research  ",
        project_id=project.id,
        user_id=1,
        scope="local",
        settings=app_settings,
    )
    assert isinstance(result, ResearchResult)
    assert result.status == "completed"
    assert result.local_count >= 2
    assert result.web_count == 0
    assert result.report.startswith("# Research report")
    assert "## Local knowledge" in result.report
    job = repo.get_research_job(db, result.job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.question == "discord research"
    assert job.scope == "local"
    assert job.provider is None
    report = repo.get_research_report(db, result.job_id)
    assert report is not None
    assert report.citation_count == result.source_count
    assert len(repo.list_research_sources(db, result.job_id)) == result.source_count
    assert (
        run_research("discord", project_id=project.id, scope="local", settings=app_settings).status
        == "completed"
    )


def test_run_research_validates_inputs(db, app_settings) -> None:
    with pytest.raises(ValueError, match="empty"):
        run_research("   ", settings=app_settings)
    with pytest.raises(ValueError, match="1000"):
        run_research("x" * 1001, settings=app_settings)
    with pytest.raises(ValueError, match="scope"):
        run_research("q", scope="everything", settings=app_settings)
    with pytest.raises(ValueError, match="not found"):
        run_research("q", project_id=999, settings=app_settings)


def test_run_research_web_only_without_provider_fails(db, app_settings) -> None:
    result = run_research("q", scope="web", settings=app_settings)
    assert result.status == "failed"
    assert result.error and "not configured" in result.error
    assert result.report == ""
    assert result.source_count == 0
    job = repo.get_research_job(db, result.job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_text == result.error


def test_run_research_both_without_web_provider_still_completes(db, app_settings) -> None:
    _seed_project(db)
    result = run_research("discord research", scope="both", settings=app_settings)
    assert result.status == "completed"
    assert result.local_count > 0
    assert result.web_count == 0
    assert "Web research skipped" in result.report
    assert "**Web provider:** not configured" in result.report


def test_run_research_both_with_web_error_still_completes(db, app_settings, monkeypatch) -> None:
    _seed_project(db)
    _fake_web(monkeypatch, error=ResearchError("provider exploded"))
    result = run_research("discord research", scope="both", settings=app_settings)
    assert result.status == "completed"
    assert "Web research failed: provider exploded" in result.report


def test_run_research_web_only_with_web_error_fails(db, app_settings, monkeypatch) -> None:
    _fake_web(monkeypatch, error=ResearchError("provider exploded"))
    result = run_research("q", scope="web", settings=app_settings)
    assert result.status == "failed"
    assert result.error == "provider exploded"
    job = repo.get_research_job(db, result.job_id)
    assert job is not None and job.status == "failed"


def test_run_research_web_only_success_stores_web_sources(db, app_settings, monkeypatch) -> None:
    findings = [
        WebFinding(
            title="Result",
            url="https://example.com/",
            snippet="snippet",
            score=1.0,
            provider="tavily",
            content="body",
            content_hash="a" * 64,
            fetched_at_utc="2026-10-20T00:00:00Z",
        )
    ]
    _fake_web(monkeypatch, findings=findings)
    result = run_research("q", scope="web", settings=app_settings)
    assert result.status == "completed"
    assert result.web_count == 1
    assert result.local_count == 0
    sources = repo.list_research_sources(db, result.job_id)
    assert len(sources) == 1
    assert sources[0].canonical_url == "https://example.com/"
    assert sources[0].content_hash == "a" * 64
    assert result.report.endswith("\n")


def test_run_research_web_source_without_hash_uses_url_hash(db, app_settings, monkeypatch) -> None:
    findings = [
        WebFinding(
            title="No hash",
            url="https://example.com/no-hash",
            snippet="snippet",
            content_hash=None,
        )
    ]
    _fake_web(monkeypatch, findings=findings)
    result = run_research("q", scope="web", settings=app_settings)
    sources = repo.list_research_sources(db, result.job_id)
    assert sources[0].content_hash == _content_hash("https://example.com/no-hash")


def test_run_research_both_success_combines_everything(db, app_settings, monkeypatch) -> None:
    _seed_project(db)
    findings = [WebFinding(title="Web", url="https://example.com/", snippet="web")]
    _fake_web(monkeypatch, findings=findings)
    result = run_research("discord research", scope="both", settings=app_settings)
    assert result.status == "completed"
    assert result.local_count > 0
    assert result.web_count == 1
    assert "## Local knowledge" in result.report
    assert "## Web sources" in result.report
    assert "**Web provider:** not configured" in result.report


def test_run_research_unexpected_error_marks_job_failed(db, app_settings, monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "research_local", explode)
    with pytest.raises(ResearchError, match="Research failed: RuntimeError"):
        run_research("q", scope="local", settings=app_settings)
    job = repo.list_recent_research_jobs(db, limit=1)[0]
    assert job.status == "failed"
    assert job.error_text == "Research failed: RuntimeError"


def test_multiple_local_sources_use_plural_summary(db, app_settings) -> None:
    project = _seed_project(db)
    result = run_research(
        "discord research", project_id=project.id, scope="local", settings=app_settings
    )
    assert result.source_count > 1
    job = repo.get_research_job(db, result.job_id)
    assert job is not None
    assert job.result_summary == f"{result.source_count} sources (3 local, 0 web)"


def test_research_history_scopes_and_limits(db, app_settings) -> None:
    project = _seed_project(db)
    first = run_research(
        "discord research", project_id=project.id, scope="local", settings=app_settings
    )
    second = run_research(
        "discord research", project_id=project.id, scope="local", settings=app_settings
    )
    global_job = repo.upsert_research_job(db, None, None, "global", scope="local")
    db.commit()
    recent = research_history(limit=100)
    assert {job.id for job in recent} >= {first.job_id, second.job_id, global_job.id}
    scoped = research_history(project.id, limit=1)
    assert len(scoped) == 1
    assert scoped[0].project_id == project.id
