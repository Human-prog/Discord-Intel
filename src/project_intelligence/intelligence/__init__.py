"""Intelligence module for Phase 13 - Evidence and Project Intelligence Engine.

Provides evidence normalization, claim tracking, facts vs inferences,
stale/conflict detection, and project summaries.
"""

from __future__ import annotations

from .evidence_engine import EvidenceClaim, ProjectIntelligence, create_intelligence

__all__ = [
    "EvidenceClaim",
    "ProjectIntelligence",
    "create_intelligence",
]
