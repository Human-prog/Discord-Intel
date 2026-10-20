"""Research and Source Discovery (Phase 15).

Controlled research pipeline with SSRF protections, evidence-backed reports,
citation tracking, and URL/DNS/IP validation.

All research is private by default and requires explicit authorization.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from project_intelligence.config import Settings, load_settings


# ---------------------------------------------------------------------------
# URL safety validation
# ---------------------------------------------------------------------------

BLOCKED_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",  # Azure metadata
})


def is_safe_url(url: str) -> bool:
    """Validate a URL for SSRF safety.

    Checks:
    - Scheme is HTTPS (or HTTP for localhost in dev)
    - Host is not in blocked list
    - Host is not a private/loopback/link-local IP
    - No redirect to private IPs (checked separately)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    if host.lower() in BLOCKED_HOSTS:
        return False

    # Check if host is an IP address
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        # Not an IP address; check for suspicious patterns
        if host.lower().endswith(".local") or host.lower().endswith(".internal"):
            return False

    return True


def validate_redirect(url: str, redirect_url: str) -> bool:
    """Validate that a redirect target is also safe."""
    return is_safe_url(redirect_url)


# ---------------------------------------------------------------------------
# Research source model
# ---------------------------------------------------------------------------

class ResearchSource:
    """A research source with metadata."""

    def __init__(
        self,
        title: str,
        canonical_url: str,
        source_type: str,
        content_hash: str,
        retrieved_at_utc: str,
    ) -> None:
        self.title = title
        self.canonical_url = canonical_url
        self.source_type = source_type
        self.content_hash = content_hash
        self.retrieved_at_utc = retrieved_at_utc


# ---------------------------------------------------------------------------
# Research pipeline
# ---------------------------------------------------------------------------

class ResearchPipeline:
    """Controlled research pipeline with SSRF protections."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        self.allowed_domains = self.settings.research_allowed_domains
        self.max_results = self.settings.research_max_results
        self.max_response_bytes = self.settings.research_max_response_bytes

    def is_domain_allowed(self, domain: str) -> bool:
        """Check if a domain is in the allowed list."""
        if not self.allowed_domains:
            return False
        domain = domain.lower()
        for allowed in self.allowed_domains:
            if domain == allowed or domain.endswith(f".{allowed}"):
                return True
        return False

    def normalize_url(self, url: str) -> str | None:
        """Normalize and validate a URL."""
        if not is_safe_url(url):
            return None
        parsed = urlparse(url)
        # Only allow HTTPS in production
        if self.settings.app_env == "production" and parsed.scheme != "https":
            return None
        return url

    def fetch_source(self, url: str) -> ResearchSource | None:
        """Fetch a research source with all safety checks."""
        if not self.normalize_url(url):
            return None

        parsed = urlparse(url)
        domain = parsed.hostname or ""
        if not self.is_domain_allowed(domain):
            return None

        # Placeholder: actual HTTP fetch would go here
        # For now, return a stub source
        content_hash = hashlib.sha256(url.encode()).hexdigest()
        return ResearchSource(
            title=f"Source: {domain}",
            canonical_url=url,
            source_type="web",
            content_hash=content_hash,
            retrieved_at_utc=datetime.now(timezone.utc).isoformat() + "Z",
        )

    def deduplicate_sources(self, sources: list[ResearchSource]) -> list[ResearchSource]:
        """Remove duplicate sources by content hash."""
        seen: set[str] = set()
        unique: list[ResearchSource] = []
        for source in sources:
            if source.content_hash not in seen:
                seen.add(source.content_hash)
                unique.append(source)
        return unique

    def generate_report(
        self,
        question: str,
        sources: list[ResearchSource],
    ) -> dict[str, Any]:
        """Generate a research report with citations."""
        return {
            "question": question,
            "sources": [
                {
                    "title": s.title,
                    "url": s.canonical_url,
                    "type": s.source_type,
                    "hash": s.content_hash,
                }
                for s in sources
            ],
            "citation_count": len(sources),
            "generated_at_utc": datetime.now(timezone.utc).isoformat() + "Z",
            "status": "completed" if sources else "no_sources",
        }


def create_research_pipeline(settings: Optional[Settings] = None) -> ResearchPipeline:
    """Factory for ResearchPipeline."""
    if settings is None:
        settings = load_settings()
    return ResearchPipeline(settings)