"""Local research over the project catalog and recorded work."""

from __future__ import annotations

import hashlib
import json

import pytest

from project_intelligence.research import local_research
from project_intelligence.research.local_research import (
    LocalFinding,
    LocalResearcher,
    build_local_report,
    research_local,
    tokenize,
    utc_now,
)
from project_intelligence.storage import repositories as repo


def _key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _seed(db):
    alpha = repo.upsert_catalog_project(
        db,
        catalog_key=_key("alpha"),
        name="Alpha research dashboard",
        description="Discord bot dashboard with a research pipeline",
        local_path="C:\\Projects\\Alpha",
        repo_url="https://example.com/alpha",
        tech_stack_json=json.dumps(["Python", "FastAPI", "discord.py"]),
        category="01 - High Priority Projects",
        priority="high",
        catalog_status="active",
        last_activity_utc="2026-10-20T00:00:00Z",
        metadata_json=json.dumps({"relative_path": "Alpha", "markers": ["pyproject.toml"]}),
    )
    beta = repo.upsert_project(db, "Beta unrelated", "gardening notes", "/srv/beta")
    repo.upsert_project(
        db,
        "Gamma discord research helper",
        "Discord research helper with no catalog metadata",
        "/srv/gamma",
    )
    repo.upsert_work_item(
        db,
        alpha.id,
        "commit",
        "Add research dashboard endpoint",
        body="Discord bot web research and local search",
        source="git",
        external_id="a" * 40,
        occurred_at_utc="2026-10-21T00:00:00Z",
    )
    repo.upsert_work_item(
        db,
        alpha.id,
        "manual",
        "Gardening chore",
        body="nothing to do with the question",
        source="manual",
    )
    repo.upsert_note(db, alpha.id, 123, "Note about the research pipeline and dashboard")
    repo.upsert_milestone(
        db,
        alpha.id,
        "Research launch",
        "Ship the Discord dashboard research view",
        "open",
        "2026-11-01",
    )
    repo.upsert_evidence(
        db,
        alpha.id,
        None,
        "Web research proof",
        "b" * 64,
        0.9,
        "The bot dashboard can research the web",
    )
    job = repo.upsert_research_job(db, alpha.id, None, "Previous research question", scope="both", provider="tavily")
    repo.upsert_research_report(db, job.id, "Earlier report about research and Discord", citation_count=1)
    global_job = repo.upsert_research_job(db, None, None, "Global research", scope="local")
    repo.upsert_research_report(db, global_job.id, "Global report about local knowledge", citation_count=1)
    db.commit()
    return alpha, beta


def test_tokenize_drops_stopwords_deduplicates_and_stems() -> None:
    assert tokenize("The RESEARCH research dashboards, and the bot!") == [
        "research",
        "dashboard",
        "bot",
    ]
    assert tokenize("a I x") == []
    assert tokenize("C++ C# .NET node.js") == ["c++", "c#", "net", "node.js"]


def test_json_helpers_handle_invalid_values() -> None:
    assert local_research._parse_metadata(None) == {}
    assert local_research._parse_metadata("{bad") == {}
    assert local_research._parse_metadata("[1, 2]") == {}
    assert local_research._parse_metadata('{"a": 1}') == {"a": 1}
    assert local_research._parse_list(None) == []
    assert local_research._parse_list("{bad") == []
    assert local_research._parse_list('{"a": 1}') == []
    assert local_research._parse_list('["Python", "", "Rust"]') == ["Python", "Rust"]


def test_snippet_and_timestamp_helpers() -> None:
    assert local_research._snippet("  hello   world ") == "hello world"
    long = "x" * 400
    assert local_research._snippet(long).endswith("…")
    assert len(local_research._snippet(long)) == 320
    assert utc_now().endswith("Z")
    assert local_research._text(None) == ""
    assert local_research._text(4) == "4"


def test_score_tokens_requires_matches_and_rewards_phrase() -> None:
    assert local_research._score_tokens([], "text", 2.0, "text") == (0.0, 0)
    assert local_research._score_tokens(["missing"], "text", 2.0, "text") == (0.0, 0)
    score, matched = local_research._score_tokens(
        ["discord", "research"], "Discord research dashboard", 2.0, "discord research"
    )
    assert matched == 2
    assert score == 6.0


def test_search_finds_every_local_source_type(db, app_settings) -> None:
    alpha, _ = _seed(db)
    researcher = LocalResearcher(app_settings)
    findings = researcher.search("discord research dashboard")
    assert findings
    source_types = {finding.source_type for finding in findings}
    assert {"project", "work", "note", "milestone", "evidence", "report"} <= source_types
    project_finding = next(f for f in findings if f.source_ref == f"project:{alpha.id}")
    assert project_finding.source_ref == f"project:{alpha.id}"
    assert project_finding.project_name == "Alpha research dashboard"
    assert "Tech: Python" in project_finding.snippet
    assert project_finding.metadata["matched_terms"] >= 1
    assert all(f.score > 0 for f in findings)


def test_search_respects_project_filter_and_limit(db, app_settings) -> None:
    alpha, beta = _seed(db)
    researcher = LocalResearcher(app_settings)
    filtered = researcher.search("discord research", project_id=beta.id)
    assert filtered == []
    limited = researcher.search("discord research", project_id=alpha.id, limit=2)
    assert len(limited) == 2
    assert all(f.project_id == alpha.id for f in limited)
    assert researcher.search("", limit=2) == []
    assert researcher.search("discord")[0].score > 0


def test_global_research_report_is_findable(db, app_settings) -> None:
    _seed(db)
    findings = LocalResearcher(app_settings).search("global local knowledge")
    reports = [finding for finding in findings if finding.source_type == "report"]
    assert reports
    assert any(finding.project_id is None for finding in reports)


def test_build_local_report_with_and_without_findings() -> None:
    empty = build_local_report("nothing", [])
    assert "No matching local records" in empty
    finding = LocalFinding(
        source_type="note",
        source_ref="note:1",
        title="Note",
        snippet="A useful note",
        score=3.5,
        project_name=None,
        occurred_at_utc=None,
    )
    report = build_local_report("useful", [finding])
    assert "[1] Note" in report
    assert "workspace" in report
    assert "`note:1`" in report
    assert "score 3.50" in report


def test_research_local_returns_findings_and_report(db, app_settings) -> None:
    _seed(db)
    findings, report = research_local("discord research", settings=app_settings, limit=3)
    assert len(findings) == 3
    assert report.startswith("# Local research")
    assert "**Question:** discord research" in report


@pytest.mark.parametrize("value", [None, 0, "", "not-json"])
def test_parse_metadata_never_raises(value) -> None:
    assert isinstance(local_research._parse_metadata(value), dict)
