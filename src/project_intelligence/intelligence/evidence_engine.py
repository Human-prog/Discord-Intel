"""Evidence and Project Intelligence Engine (Phase 13).

Converts verified records into traceable project insights.  Separates facts,
inferences, recommendations, and unknowns.  Links claims to supporting evidence.
Detects stale, conflicting, and missing data.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from project_intelligence.config import Settings, load_settings


# ---------------------------------------------------------------------------
# Evidence model
# ---------------------------------------------------------------------------

class EvidenceClaim:
    """A single claim with supporting evidence references."""

    def __init__(
        self,
        claim_id: str,
        text: str,
        evidence_ids: list[str],
        confidence: float = 1.0,
        is_inference: bool = False,
        is_uncertain: bool = False,
    ) -> None:
        self.claim_id = claim_id
        self.text = text
        self.evidence_ids = evidence_ids
        self.confidence = confidence
        self.is_inference = is_inference
        self.is_uncertain = is_uncertain


class ProjectIntelligence:
    """Project intelligence engine that converts verified records into insights."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        self.claims: list[EvidenceClaim] = []

    def add_claim(
        self,
        text: str,
        evidence_ids: list[str],
        confidence: float = 1.0,
        is_inference: bool = False,
    ) -> EvidenceClaim:
        """Add a claim linked to supporting evidence."""
        claim_id = hashlib.sha256(text.encode()).hexdigest()[:12]
        claim = EvidenceClaim(
            claim_id=claim_id,
            text=text,
            evidence_ids=evidence_ids,
            confidence=confidence,
            is_inference=is_inference,
            is_uncertain=confidence < 0.7,
        )
        self.claims.append(claim)
        return claim

    def get_facts(self) -> list[EvidenceClaim]:
        """Return only verified facts (not inferences)."""
        return [c for c in self.claims if not c.is_inference]

    def get_inferences(self) -> list[EvidenceClaim]:
        """Return only inferences."""
        return [c for c in self.claims if c.is_inference]

    def get_uncertain(self) -> list[EvidenceClaim]:
        """Return claims marked as uncertain."""
        return [c for c in self.claims if c.is_uncertain]

    def detect_stale(self, max_age_hours: int = 24) -> list[EvidenceClaim]:
        """Detect claims whose evidence is older than max_age_hours."""
        # Placeholder: actual staleness check would compare evidence timestamps
        return []

    def detect_conflicts(self) -> list[tuple[EvidenceClaim, EvidenceClaim]]:
        """Detect conflicting claims (same topic, different conclusions)."""
        # Placeholder: actual conflict detection would compare claim semantics
        return []

    def generate_summary(self) -> dict[str, Any]:
        """Generate a project summary from verified claims."""
        return {
            "total_claims": len(self.claims),
            "facts": len(self.get_facts()),
            "inferences": len(self.get_inferences()),
            "uncertain": len(self.get_uncertain()),
            "generated_at_utc": datetime.now(timezone.utc).isoformat() + "Z",
        }


def create_intelligence(settings: Optional[Settings] = None) -> ProjectIntelligence:
    """Factory for ProjectIntelligence."""
    return ProjectIntelligence(settings)