"""Intelligence module for Phase 13 — Evidence and Project Intelligence Engine.

Provides evidence normalization, claim tracking, facts vs inferences,
stale/conflict detection, and project summaries.
"""

from __future__ import annotations

from .evidence_engine import ProjectIntelligence, EvidenceClaim, create_intelligence  # noqa: F401

__all__ = [
    "ProjectIntelligence",
    "EvidenceClaim",
    "create_intelligence",
]