"""Controlled web research with SSRF-safe fetching and citation tracking.

The web researcher has two independent halves:

* a search provider (Tavily or Brave) that returns candidate result URLs;
* a fetcher that re-validates every URL, resolves DNS, refuses non-public
  addresses, follows redirects manually, and bounds the response size.

Search results and page contents are untrusted data.  They are stored with
their source URL and a retrieval timestamp, never executed or interpreted as
instructions.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

import httpx

from project_intelligence.config import Settings, load_settings
from project_intelligence.research.research_pipeline import is_safe_url

_MAX_REDIRECTS = 4
_MAX_TEXT_CHARS = 20_000
_ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/json",
    "application/xml",
    "text/xml",
)


class ResearchError(Exception):
    """Safe, user-presentable research failure (never contains secrets)."""


class ResearchNotConfigured(ResearchError):
    """Raised when web research was requested without a provider/key."""


@dataclass
class WebFinding:
    """One search result, optionally enriched with fetched page text."""

    title: str
    url: str
    snippet: str
    score: float = 0.0
    provider: str = ""
    content: str | None = None
    content_hash: str | None = None
    fetched_at_utc: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebPage:
    """A bounded, text-only view of one fetched page."""

    url: str
    title: str
    text: str
    content_hash: str
    content_type: str
    fetched_at_utc: str
    status_code: int


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# HTML to text
# ---------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    """Extract visible text and the document title from HTML."""

    _SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "canvas", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "section"}:
            self._text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "section"}:
            self._text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._skip_depth:
            return
        self._text_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self._title_parts).split())

    @property
    def text(self) -> str:
        return " ".join("".join(self._text_parts).split())


def html_to_text(html: str) -> tuple[str, str]:
    """Return ``(title, visible_text)`` for an HTML document."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: S110 - best-effort parse of untrusted, malformed HTML
        # Return whatever was parsed before the failure.
        pass
    return parser.title, parser.text


def _host_is_public(host: str, port: int, resolver: Any = socket.getaddrinfo) -> bool:
    """Resolve *host* and require every address to be globally routable."""
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError):
        return False
    if not infos:
        return False
    for info in infos:
        raw = str(info[4][0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            return False
        if not address.is_global:
            return False
    return True


def _domain_allowed(host: str, allowed_domains: list[str]) -> bool:
    """An empty allowlist means the configured search provider chooses."""
    if not allowed_domains:
        return True
    lowered = host.lower()
    return any(lowered == allowed or lowered.endswith(f".{allowed}") for allowed in allowed_domains)


# ---------------------------------------------------------------------------
# Search providers
# ---------------------------------------------------------------------------


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, max_results: int) -> list[WebFinding]:  # pragma: no cover
        ...


class TavilyProvider:
    """Tavily search API (https://docs.tavily.com)."""

    name = "tavily"
    endpoint = "https://api.tavily.com/search"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.settings.http_timeout_seconds,
                headers={"User-Agent": "DiscordProjectIntelligence/0.1"},
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def search(self, query: str, *, max_results: int) -> list[WebFinding]:
        if self.settings.research_api_key is None:
            raise ResearchNotConfigured("Tavily is selected but RESEARCH_API_KEY is unset")
        payload = {
            "api_key": self.settings.research_api_key.get_secret_value(),
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            response = self._http().post(self.endpoint, json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ResearchError(f"Tavily search failed: {type(exc).__name__}") from None

        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise ResearchError("Tavily returned an unexpected response")
        findings: list[WebFinding] = []
        for item in results[:max_results]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            findings.append(
                WebFinding(
                    title=str(item.get("title") or url)[:300],
                    url=url,
                    snippet=str(item.get("content") or "")[:1200],
                    score=float(item.get("score") or 0.0),
                    provider=self.name,
                )
            )
        return findings


class BraveProvider:
    """Brave Search API (https://api.search.brave.com)."""

    name = "brave"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.settings.http_timeout_seconds,
                headers={"User-Agent": "DiscordProjectIntelligence/0.1"},
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def search(self, query: str, *, max_results: int) -> list[WebFinding]:
        if self.settings.research_api_key is None:
            raise ResearchNotConfigured("Brave is selected but RESEARCH_API_KEY is unset")
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.settings.research_api_key.get_secret_value(),
        }
        try:
            response = self._http().get(
                self.endpoint,
                params={"q": query, "count": max_results},
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ResearchError(f"Brave search failed: {type(exc).__name__}") from None

        web = body.get("web") if isinstance(body, dict) else None
        results = web.get("results") if isinstance(web, dict) else None
        if not isinstance(results, list):
            raise ResearchError("Brave returned an unexpected response")
        findings: list[WebFinding] = []
        for index, item in enumerate(results[:max_results]):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            findings.append(
                WebFinding(
                    title=str(item.get("title") or url)[:300],
                    url=url,
                    snippet=str(item.get("description") or "")[:1200],
                    score=float(max_results - index),
                    provider=self.name,
                )
            )
        return findings


def provider_from_settings(settings: Settings) -> SearchProvider:
    """Build the configured provider or fail with a safe message."""
    name = (settings.research_provider or "").strip().lower()
    if not name or name == "none":
        raise ResearchNotConfigured(
            "Web research is not configured. Set RESEARCH_PROVIDER to tavily or brave and provide RESEARCH_API_KEY."
        )
    if name == "tavily":
        return TavilyProvider(settings)
    if name == "brave":
        return BraveProvider(settings)
    raise ResearchNotConfigured("Unknown RESEARCH_PROVIDER. Supported values are: tavily, brave, none.")


# ---------------------------------------------------------------------------
# Safe fetcher
# ---------------------------------------------------------------------------


class SafeFetcher:
    """Fetch public web pages while enforcing SSRF and size limits."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        resolver: Any = socket.getaddrinfo,
    ) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None
        self._resolver = resolver

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.settings.http_timeout_seconds,
                follow_redirects=False,
                headers={
                    "User-Agent": "DiscordProjectIntelligence/0.1 (+private research)",
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                },
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _validate_url(self, url: str) -> str:
        if not is_safe_url(url):
            raise ResearchError("Refusing to fetch an unsafe or non-public URL")
        parsed = urlparse(url)
        if parsed.scheme == "http" and self.settings.app_env == "production":
            raise ResearchError("Only HTTPS URLs are allowed in production")
        host = parsed.hostname or ""
        if not _domain_allowed(host, self.settings.research_allowed_domains):
            raise ResearchError(f"Domain is not in RESEARCH_ALLOWED_DOMAINS: {host}")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            raise ResearchError("URL has an invalid port") from None
        if not _host_is_public(host, port, self._resolver):
            raise ResearchError("Refusing to fetch a host that resolves to a non-public address")
        return url

    def fetch(self, url: str) -> WebPage:
        current = self._validate_url(url)
        for _ in range(_MAX_REDIRECTS + 1):
            try:
                with self._http().stream("GET", current) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise ResearchError("Redirect response had no Location header")
                        current = self._validate_url(urljoin(current, location))
                        continue
                    if response.status_code >= 400:
                        raise ResearchError(f"Source returned HTTP {response.status_code}")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if not any(content_type.startswith(allowed) for allowed in _ALLOWED_CONTENT_TYPES):
                        raise ResearchError(f"Unsupported content type: {content_type or 'unknown'}")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > self.settings.research_max_response_bytes:
                            raise ResearchError("Source exceeded the configured response size limit")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    break
            except httpx.HTTPError as exc:
                raise ResearchError(f"Could not fetch source: {type(exc).__name__}") from None
        else:
            raise ResearchError("Too many redirects")

        encoding = "utf-8"
        try:
            text = raw.decode(encoding, errors="replace")
        except LookupError:  # pragma: no cover - utf-8 is always available
            text = raw.decode(errors="replace")
        if content_type.startswith("text/html") or content_type.endswith("xhtml+xml"):
            title, visible = html_to_text(text)
        else:
            title, visible = "", " ".join(text.split())
        visible = visible[:_MAX_TEXT_CHARS]
        digest = hashlib.sha256(raw).hexdigest()
        return WebPage(
            url=current,
            title=(title or urlparse(current).hostname or current)[:300],
            text=visible,
            content_hash=digest,
            content_type=content_type,
            fetched_at_utc=_utc_now(),
            status_code=response.status_code,
        )


# ---------------------------------------------------------------------------
# Web research orchestration
# ---------------------------------------------------------------------------


def build_web_report(question: str, findings: list[WebFinding], provider: str) -> str:
    """Render web findings as a cited Markdown report."""
    lines = [
        "# Web research",
        "",
        f"**Question:** {question}",
        f"**Provider:** {provider}",
        "",
    ]
    if not findings:
        lines.append("The search provider returned no usable public sources.")
        return "\n".join(lines)

    lines.append(
        f"Found **{len(findings)}** source{'' if len(findings) == 1 else 's'}. "
        "Snippets below are quoted from the source; content is untrusted."
    )
    lines.append("")
    for index, finding in enumerate(findings, start=1):
        lines.append(f"### [{index}] {finding.title}")
        lines.append(f"<{finding.url}>")
        lines.append("")
        if finding.snippet:
            lines.append(f"> {finding.snippet.strip()}")
            lines.append("")
        if finding.content:
            excerpt = finding.content[:1200].strip()
            lines.append(excerpt + ("…" if len(finding.content) > 1200 else ""))
            lines.append("")
        meta = [f"source: {finding.provider}"]
        if finding.fetched_at_utc:
            meta.append(f"fetched: {finding.fetched_at_utc}")
        if finding.content_hash:
            meta.append(f"sha256: {finding.content_hash[:16]}…")
        lines.append(f"*{' · '.join(meta)}*")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def research_web(
    question: str,
    *,
    settings: Settings | None = None,
    provider: SearchProvider | None = None,
    fetcher: SafeFetcher | None = None,
    max_results: int | None = None,
    fetch_top: int = 5,
) -> tuple[list[WebFinding], str]:
    """Search the web, fetch the top public sources, and build a cited report."""
    settings = settings or load_settings()
    limit = max(1, min(max_results or settings.research_max_results, 20))
    owns_provider = provider is None
    owns_fetcher = fetcher is None
    provider = provider or provider_from_settings(settings)
    fetcher = fetcher or SafeFetcher(settings)
    try:
        try:
            findings = provider.search(question, max_results=limit)
        except ResearchNotConfigured:
            raise
        except ResearchError:
            raise
        except Exception as exc:  # pragma: no cover - defensive boundary
            raise ResearchError(f"Web search failed: {type(exc).__name__}") from None

        usable: list[WebFinding] = []
        for finding in findings:
            if not is_safe_url(finding.url):
                continue
            usable.append(finding)
        usable = usable[:limit]
        for finding in usable[: max(0, min(fetch_top, len(usable)))]:
            try:
                page = fetcher.fetch(finding.url)
            except ResearchError:
                # A search result remains a valid citation even when the page
                # is unreachable or blocked; keep its provider snippet.
                continue
            finding.url = page.url
            finding.content = page.text
            finding.content_hash = page.content_hash
            finding.fetched_at_utc = page.fetched_at_utc
            if page.title and page.title != page.url:
                finding.title = page.title
            if not finding.snippet:
                finding.snippet = page.text[:600]
        return usable, build_web_report(question, usable, provider.name)
    finally:
        if owns_fetcher:
            fetcher.close()
        if owns_provider and hasattr(provider, "close"):
            provider.close()


def research_status(settings: Settings) -> dict[str, object]:
    """Return a secret-free description of the research configuration."""
    provider = (settings.research_provider or "none").lower()
    return {
        "provider": provider,
        "configured": provider in {"tavily", "brave"} and settings.research_api_key is not None,
        "allowed_domains": list(settings.research_allowed_domains),
        "max_results": settings.research_max_results,
        "allowlist_mode": "restricted" if settings.research_allowed_domains else "provider",
    }
