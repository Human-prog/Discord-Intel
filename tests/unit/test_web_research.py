"""Controlled web research: providers, SSRF-safe fetching, and reports."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from project_intelligence.research import web_research
from project_intelligence.research.web_research import (
    BraveProvider,
    ResearchError,
    ResearchNotConfigured,
    SafeFetcher,
    TavilyProvider,
    WebFinding,
    WebPage,
    build_web_report,
    html_to_text,
    provider_from_settings,
    research_status,
    research_web,
)

PUBLIC = [(2, 1, 6, "", ("93.184.216.34", 0))]


def public_resolver(host, port, type=None):
    return PUBLIC


def private_resolver(host, port, type=None):
    return [(2, 1, 6, "", ("10.0.0.5", 0))]


def failing_resolver(host, port, type=None):
    raise OSError("dns failed")


def invalid_resolver(host, port, type=None):
    return [(2, 1, 6, "", ("not-an-ip", 0))]


def empty_resolver(host, port, type=None):
    return []


def _transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# HTML extraction and address validation
# ---------------------------------------------------------------------------


def test_html_to_text_extracts_title_and_visible_text() -> None:
    title, text = html_to_text(
        "<html><head><title>My Page</title></head><body>"
        "<script>ignore()</script><style>.x{}</style><h1>Hello</h1><p>World</p>"
        "</body></html>"
    )
    assert title == "My Page"
    assert "Hello" in text
    assert "World" in text
    assert "ignore" not in text


def test_html_to_text_survives_parser_failure(monkeypatch) -> None:
    def explode(self, data):
        raise RuntimeError("bad markup")

    monkeypatch.setattr(web_research._TextExtractor, "feed", explode)
    title, text = html_to_text("<html><title>T</title><p>Body</p></html>")
    assert title == ""
    assert text == ""


def test_host_is_public_handles_every_address_shape() -> None:
    assert web_research._host_is_public("example.com", 443, public_resolver) is True
    assert web_research._host_is_public("example.com", 443, private_resolver) is False
    assert web_research._host_is_public("example.com", 443, failing_resolver) is False
    assert web_research._host_is_public("example.com", 443, invalid_resolver) is False
    assert web_research._host_is_public("example.com", 443, empty_resolver) is False


def test_domain_allowlist_modes() -> None:
    assert web_research._domain_allowed("anything.example", []) is True
    assert web_research._domain_allowed("example.com", ["example.com"]) is True
    assert web_research._domain_allowed("docs.example.com", ["example.com"]) is True
    assert web_research._domain_allowed("evil.com", ["example.com"]) is False


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def test_tavily_requires_key(make_settings) -> None:
    provider = TavilyProvider(make_settings())
    with pytest.raises(ResearchNotConfigured):
        provider.search("q", max_results=3)


def test_tavily_parses_results(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.tavily.com/search"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "One", "url": "https://example.com/1", "content": "A", "score": 0.9},
                    "not-a-dict",
                    {"title": "No URL", "content": "ignored"},
                ]
            },
        )

    provider = TavilyProvider(
        make_settings(research_api_key="secret", research_provider="tavily"),
        client=_transport(handler),
    )
    findings = provider.search("q", max_results=5)
    assert [finding.title for finding in findings] == ["One"]
    assert findings[0].provider == "tavily"
    assert findings[0].score == 0.9


def test_tavily_errors_are_safe(make_settings) -> None:
    settings = make_settings(research_api_key="secret", research_provider="tavily")
    for handler in (
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(200, content=b"not json"),
        lambda request: httpx.Response(200, json={"results": "nope"}),
    ):
        provider = TavilyProvider(settings, client=_transport(handler))
        with pytest.raises(ResearchError):
            provider.search("q", max_results=3)


def test_tavily_owned_client_closes(make_settings) -> None:
    provider = TavilyProvider(make_settings(research_api_key="secret"))
    owned = provider._http()
    owned.close()
    provider._client = _transport(lambda request: httpx.Response(200, json={"results": []}))
    provider._owns_client = True
    provider.close()
    assert provider._client is None
    provider.close()
    assert provider._client is None


def test_brave_requires_key_and_parses(make_settings) -> None:
    provider = BraveProvider(make_settings())
    with pytest.raises(ResearchNotConfigured):
        provider.search("q", max_results=3)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-subscription-token"] == "secret"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"title": "One", "url": "https://example.com/1", "description": "A"},
                        "bad",
                        {"title": "No URL"},
                    ]
                }
            },
        )

    brave = BraveProvider(
        make_settings(research_api_key="secret", research_provider="brave"),
        client=_transport(handler),
    )
    findings = brave.search("q", max_results=5)
    assert [finding.title for finding in findings] == ["One"]
    assert findings[0].provider == "brave"


def test_brave_errors_are_safe(make_settings) -> None:
    settings = make_settings(research_api_key="secret", research_provider="brave")
    for handler in (
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(200, content=b"not json"),
        lambda request: httpx.Response(200, json={"web": {"results": "nope"}}),
        lambda request: httpx.Response(200, json={"web": "nope"}),
    ):
        provider = BraveProvider(settings, client=_transport(handler))
        with pytest.raises(ResearchError):
            provider.search("q", max_results=3)


def test_brave_owned_client_closes(make_settings) -> None:
    provider = BraveProvider(make_settings(research_api_key="secret"))
    owned = provider._http()
    owned.close()
    provider._client = _transport(lambda request: httpx.Response(200, json={"web": {"results": []}}))
    provider._owns_client = True
    provider.close()
    assert provider._client is None
    provider.close()
    assert provider._client is None


def test_provider_from_settings(make_settings) -> None:
    with pytest.raises(ResearchNotConfigured):
        provider_from_settings(make_settings())
    with pytest.raises(ResearchNotConfigured):
        provider_from_settings(make_settings(research_provider="none"))
    with pytest.raises(ResearchNotConfigured, match="Unknown RESEARCH_PROVIDER"):
        provider_from_settings(SimpleNamespace(research_provider="unknown"))
    assert isinstance(provider_from_settings(make_settings(research_provider="tavily")), TavilyProvider)
    assert isinstance(provider_from_settings(make_settings(research_provider="brave")), BraveProvider)


# ---------------------------------------------------------------------------
# SafeFetcher
# ---------------------------------------------------------------------------


def _fetcher(settings, handler, resolver=public_resolver) -> SafeFetcher:
    return SafeFetcher(settings, client=_transport(handler), resolver=resolver)


def test_validate_url_rejects_unsafe_and_non_public(make_settings) -> None:
    settings = make_settings()
    fetcher = _fetcher(settings, lambda request: httpx.Response(200))
    for url in (
        "http://localhost/",
        "http://127.0.0.1/",
        "ftp://example.com/file",
        "https://example.com:bad/",
    ):
        with pytest.raises(ResearchError):
            fetcher._validate_url(url)
    with pytest.raises(ResearchError):
        _fetcher(settings, lambda request: httpx.Response(200), private_resolver)._validate_url("https://example.com/")
    with pytest.raises(ResearchError):
        _fetcher(
            make_settings(research_allowed_domains=["allowed.example"]),
            lambda request: httpx.Response(200),
        )._validate_url("https://evil.example/")


def test_validate_url_honours_production_https(make_settings, tmp_path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("s" * 64, encoding="utf-8")
    production = make_settings(
        app_env="production",
        data_dir=tmp_path,
        database_path=tmp_path / "db.sqlite3",
        dashboard_session_secret_file=secret,
        project_allowed_roots=[tmp_path],
        discord_owner_user_ids=[1],
    )
    fetcher = _fetcher(production, lambda request: httpx.Response(200))
    with pytest.raises(ResearchError):
        fetcher._validate_url("http://example.com/")
    assert fetcher._validate_url("https://example.com/") == "https://example.com/"


def test_fetch_html_and_plain_text(make_settings) -> None:
    settings = make_settings()

    def html_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><head><title>Title</title></head><body><p>Body text</p></body></html>",
        )

    page = _fetcher(settings, html_handler).fetch("https://example.com/page")
    assert page.title == "Title"
    assert "Body text" in page.text
    assert page.status_code == 200
    assert len(page.content_hash) == 64

    def text_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"plain   text\nhere",
        )

    page = _fetcher(settings, text_handler).fetch("https://example.com/plain")
    assert page.text == "plain text here"


def test_fetch_follows_safe_redirects(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"done")

    page = _fetcher(make_settings(), handler).fetch("https://example.com/start")
    assert page.url == "https://example.com/final"
    assert page.text == "done"


def test_fetch_rejects_bad_redirects(make_settings) -> None:
    settings = make_settings()
    with pytest.raises(ResearchError, match="no Location"):
        _fetcher(settings, lambda request: httpx.Response(302)).fetch("https://example.com/")
    with pytest.raises(ResearchError, match="Too many redirects"):
        _fetcher(
            settings,
            lambda request: httpx.Response(302, headers={"location": "https://example.com/loop"}),
        ).fetch("https://example.com/loop")


def test_fetch_rejects_error_status_content_type_and_size(make_settings) -> None:
    settings = make_settings(research_max_response_bytes=10_000)
    with pytest.raises(ResearchError, match="HTTP 404"):
        _fetcher(settings, lambda request: httpx.Response(404)).fetch("https://example.com/")
    with pytest.raises(ResearchError, match="Unsupported content type"):
        _fetcher(
            settings,
            lambda request: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf"),
        ).fetch("https://example.com/")
    with pytest.raises(ResearchError, match="size limit"):
        _fetcher(
            settings,
            lambda request: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"x" * 20_000),
        ).fetch("https://example.com/")


def test_fetch_wraps_transport_errors(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ResearchError, match="Could not fetch"):
        _fetcher(make_settings(), handler).fetch("https://example.com/")


def test_safe_fetcher_closes_owned_client(make_settings) -> None:
    fetcher = SafeFetcher(make_settings())
    owned = fetcher._http()
    owned.close()
    fetcher._client = _transport(lambda request: httpx.Response(200))
    fetcher._owns_client = True
    fetcher.close()
    assert fetcher._client is None
    fetcher.close()
    assert fetcher._client is None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class FakeProvider:
    name = "fake"

    def __init__(self, findings=None, error=None) -> None:
        self.findings = findings or []
        self.error = error
        self.closed = False

    def search(self, query: str, *, max_results: int):
        if self.error is not None:
            raise self.error
        return list(self.findings[:max_results])

    def close(self) -> None:
        self.closed = True


class FakeFetcher:
    def __init__(self, pages=None, error=None) -> None:
        self.pages = pages or {}
        self.error = error
        self.closed = False
        self.fetched: list[str] = []

    def fetch(self, url: str) -> WebPage:
        self.fetched.append(url)
        if self.error is not None:
            raise self.error
        return self.pages[url]

    def close(self) -> None:
        self.closed = True


def test_build_web_report_empty_and_populated() -> None:
    empty = build_web_report("q", [], "tavily")
    assert "no usable public sources" in empty
    finding = WebFinding(
        title="Title",
        url="https://example.com/",
        snippet="Snippet",
        provider="tavily",
        content="Long content",
        content_hash="a" * 64,
        fetched_at_utc="2026-10-20T00:00:00Z",
    )
    report = build_web_report("q", [finding], "tavily")
    assert "[1] Title" in report
    assert "Snippet" in report
    assert "Long content" in report
    assert "sha256:" in report
    no_snippet = WebFinding(
        title="Bare",
        url="https://example.com/bare",
        snippet="",
        provider="tavily",
        content=None,
    )
    assert "### [1] Bare" in build_web_report("q", [no_snippet], "tavily")


def test_research_web_enriches_results_and_skips_unsafe(make_settings) -> None:
    findings = [
        WebFinding(title="Safe", url="https://example.com/safe", snippet="", score=1.0),
        WebFinding(title="Unsafe", url="http://127.0.0.1/", snippet="bad"),
        WebFinding(title="Fails", url="https://example.com/fails", snippet="fallback"),
    ]
    provider = FakeProvider(findings)
    fetcher = FakeFetcher(
        pages={
            "https://example.com/safe": WebPage(
                url="https://example.com/safe",
                title="Fetched title",
                text="Fetched body",
                content_hash="b" * 64,
                content_type="text/html",
                fetched_at_utc="2026-10-20T00:00:00Z",
                status_code=200,
            )
        },
        error=None,
    )
    # Make the second fetch fail, exercising the snippet fallback.
    original_fetch = fetcher.fetch
    calls = {"n": 0}

    def fetch(url: str) -> WebPage:
        calls["n"] += 1
        if "fails" in url:
            raise ResearchError("unreachable")
        return original_fetch(url)

    fetcher.fetch = fetch  # type: ignore[method-assign]
    usable, report = research_web(
        "q",
        settings=make_settings(),
        provider=provider,
        fetcher=fetcher,
        max_results=3,
        fetch_top=2,
    )
    assert [finding.title for finding in usable] == ["Fetched title", "Fails"]
    assert usable[0].content == "Fetched body"
    assert usable[1].snippet == "fallback"
    assert "Fetched body" in report
    assert calls["n"] == 2
    assert provider.closed is False
    assert fetcher.closed is False


def test_research_web_propagates_provider_errors(make_settings) -> None:
    with pytest.raises(ResearchNotConfigured):
        research_web("q", settings=make_settings())
    with pytest.raises(ResearchNotConfigured):
        research_web(
            "q",
            settings=make_settings(),
            provider=FakeProvider(error=ResearchNotConfigured("no key")),
            fetcher=FakeFetcher(),
        )
    with pytest.raises(ResearchError):
        research_web(
            "q",
            settings=make_settings(),
            provider=FakeProvider(error=ResearchError("bad")),
            fetcher=FakeFetcher(),
        )

    class Exploding:
        name = "boom"

        def search(self, query, *, max_results):
            raise RuntimeError("unexpected")

    with pytest.raises(ResearchError, match="Web search failed"):
        research_web("q", settings=make_settings(), provider=Exploding(), fetcher=FakeFetcher())


def test_research_web_keeps_title_when_page_title_is_url(make_settings) -> None:
    url = "https://example.com/page"
    findings = [WebFinding(title="Search title", url=url, snippet="")]
    fetcher = FakeFetcher(
        pages={
            url: WebPage(
                url=url,
                title=url,
                text="body",
                content_hash="d" * 64,
                content_type="text/html",
                fetched_at_utc="now",
                status_code=200,
            )
        }
    )
    usable, _ = research_web("q", settings=make_settings(), provider=FakeProvider(findings), fetcher=fetcher)
    assert usable[0].title == "Search title"


def test_research_web_closes_owned_dependencies(make_settings, monkeypatch) -> None:
    provider = FakeProvider([WebFinding(title="T", url="https://example.com/", snippet="s")])
    fetcher = FakeFetcher(
        pages={
            "https://example.com/": WebPage(
                url="https://example.com/",
                title="T",
                text="body",
                content_hash="c" * 64,
                content_type="text/html",
                fetched_at_utc="now",
                status_code=200,
            )
        }
    )
    monkeypatch.setattr(web_research, "provider_from_settings", lambda settings: provider)
    monkeypatch.setattr(web_research, "SafeFetcher", lambda settings: fetcher)
    research_web("q", settings=make_settings())
    assert provider.closed is True
    assert fetcher.closed is True


def test_research_status_never_exposes_key(make_settings) -> None:
    status = research_status(make_settings())
    assert status["configured"] is False
    configured = research_status(make_settings(research_provider="tavily", research_api_key="secret"))
    assert configured["configured"] is True
    assert "secret" not in repr(configured)
