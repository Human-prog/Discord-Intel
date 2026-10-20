"""Research module for Phase 15 — Research and Source Discovery.

Provides controlled research pipeline with SSRF protections, evidence-backed
reports, citation tracking, and URL/DNS/IP validation.
"""

from __future__ import annotations

from .research_pipeline import (
    ResearchPipeline,
    ResearchSource,
    create_research_pipeline,
    is_safe_url,
    validate_redirect,
)  # noqa: F401

__all__ = [
    "ResearchPipeline",
    "ResearchSource",
    "create_research_pipeline",
    "is_safe_url",
    "validate_redirect",
]