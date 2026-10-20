"""Controlled research pipeline tests (Phase 14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_intelligence.research.research_pipeline import (
    ResearchPipeline,
    ResearchSource,
    create_research_pipeline,
    is_safe_url,
    validate_redirect,
)

# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/page",
        "https://docs.python.org/3/",
        "http://example.com/page",
    ],
)
def test_safe_urls_are_allowed(url: str) -> None:
    assert is_safe_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://0.0.0.0/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://printer.local/",
        "http://service.internal/",
    ],
)
def test_unsafe_urls_are_rejected(url: str) -> None:
    assert is_safe_url(url) is False


def test_redirect_validation_reuses_url_checks() -> None:
    assert validate_redirect("https://example.com", "https://example.com/next") is True
    assert validate_redirect("https://example.com", "http://127.0.0.1/next") is False


# ---------------------------------------------------------------------------
# Domain allowlisting
# ---------------------------------------------------------------------------


def test_domain_allowlist_matches_exact_and_subdomains(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings(research_allowed_domains=["example.com"]))
    assert pipeline.is_domain_allowed("example.com") is True
    assert pipeline.is_domain_allowed("docs.example.com") is True
    assert pipeline.is_domain_allowed("EXAMPLE.COM") is True
    assert pipeline.is_domain_allowed("evil-example.com") is False
    assert pipeline.is_domain_allowed("example.org") is False


def test_empty_domain_allowlist_denies_everything(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings(research_allowed_domains=[]))
    assert pipeline.is_domain_allowed("example.com") is False


# ---------------------------------------------------------------------------
# URL normalization and fetching
# ---------------------------------------------------------------------------


def test_normalize_url_rejects_unsafe(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings())
    assert pipeline.normalize_url("https://example.com/page") == "https://example.com/page"
    assert pipeline.normalize_url("http://127.0.0.1/") is None


def test_production_requires_https(make_settings, tmp_path: Path) -> None:
    settings = make_settings(
        app_env="production",
        data_dir=tmp_path,
        database_path=tmp_path / "db.sqlite3",
        dashboard_session_secret_file=tmp_path / "session_secret",
    )
    pipeline = ResearchPipeline(settings)
    assert pipeline.normalize_url("https://example.com/page") == "https://example.com/page"
    assert pipeline.normalize_url("http://example.com/page") is None


def test_fetch_source_returns_stub_for_allowed_domain(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings(research_allowed_domains=["example.com"]))
    source = pipeline.fetch_source("https://example.com/article")
    assert source is not None
    assert source.canonical_url == "https://example.com/article"
    assert source.title == "Source: example.com"
    assert source.source_type == "web"
    assert len(source.content_hash) == 64
    assert source.retrieved_at_utc.endswith("Z")


def test_fetch_source_refuses_disallowed_domain(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings(research_allowed_domains=["example.com"]))
    assert pipeline.fetch_source("https://evil.org/article") is None


def test_fetch_source_refuses_private_networks(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings(research_allowed_domains=["127.0.0.1"]))
    assert pipeline.fetch_source("http://127.0.0.1/admin") is None


# ---------------------------------------------------------------------------
# Deduplication and reports
# ---------------------------------------------------------------------------


def _source(title: str, url: str, content_hash: str) -> ResearchSource:
    return ResearchSource(
        title=title,
        canonical_url=url,
        source_type="web",
        content_hash=content_hash,
        retrieved_at_utc="2026-01-01T00:00:00Z",
    )


def test_deduplicate_sources_keeps_first_of_each_hash(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings())
    sources = [
        _source("A", "https://a.example", "hash-1"),
        _source("A duplicate", "https://b.example", "hash-1"),
        _source("C", "https://c.example", "hash-2"),
    ]
    unique = pipeline.deduplicate_sources(sources)
    assert [source.title for source in unique] == ["A", "C"]


def test_generate_report_with_sources(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings())
    report = pipeline.generate_report("What next?", [_source("A", "https://a.example", "h")])
    assert report["status"] == "completed"
    assert report["citation_count"] == 1
    assert report["question"] == "What next?"
    assert report["generated_at_utc"].endswith("Z")
    assert report["sources"][0]["hash"] == "h"


def test_generate_report_without_sources(make_settings) -> None:
    pipeline = ResearchPipeline(make_settings())
    report = pipeline.generate_report("What next?", [])
    assert report["status"] == "no_sources"
    assert report["citation_count"] == 0


def test_factory_returns_pipeline(make_settings) -> None:
    pipeline = create_research_pipeline(make_settings())
    assert isinstance(pipeline, ResearchPipeline)
