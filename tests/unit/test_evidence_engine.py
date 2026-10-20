"""Evidence and project intelligence engine tests (Phase 13)."""

from __future__ import annotations

from project_intelligence.intelligence.evidence_engine import (
    EvidenceClaim,
    ProjectIntelligence,
    create_intelligence,
)


def test_add_claim_links_evidence_and_hashes_text(make_settings) -> None:
    engine = ProjectIntelligence(make_settings())
    claim = engine.add_claim("The build passes", ["ev-1", "ev-2"], confidence=0.95)

    assert len(claim.claim_id) == 12
    assert claim.evidence_ids == ["ev-1", "ev-2"]
    assert claim.confidence == 0.95
    assert claim.is_inference is False
    assert claim.is_uncertain is False


def test_claim_ids_are_stable_for_the_same_text(make_settings) -> None:
    engine = ProjectIntelligence(make_settings())
    first = engine.add_claim("Same text", ["ev-1"])
    second = engine.add_claim("Same text", ["ev-2"])
    assert first.claim_id == second.claim_id


def test_low_confidence_claims_are_uncertain(make_settings) -> None:
    engine = ProjectIntelligence(make_settings())
    claim = engine.add_claim("Maybe", ["ev-1"], confidence=0.4)
    assert claim.is_uncertain is True
    assert engine.get_uncertain() == [claim]


def test_facts_and_inferences_are_separated(make_settings) -> None:
    engine = ProjectIntelligence(make_settings())
    fact = engine.add_claim("Fact", ["ev-1"], confidence=1.0)
    inference = engine.add_claim("Inference", ["ev-1"], confidence=0.9, is_inference=True)

    assert engine.get_facts() == [fact]
    assert engine.get_inferences() == [inference]
    assert engine.get_uncertain() == []


def test_summary_counts_claims(make_settings) -> None:
    engine = ProjectIntelligence(make_settings())
    engine.add_claim("Fact", ["ev-1"])
    engine.add_claim("Inference", ["ev-1"], is_inference=True)
    engine.add_claim("Uncertain", ["ev-2"], confidence=0.2)

    summary = engine.generate_summary()
    assert summary["total_claims"] == 3
    assert summary["facts"] == 2
    assert summary["inferences"] == 1
    assert summary["uncertain"] == 1
    assert summary["generated_at_utc"].endswith("Z")


def test_empty_engine_summary(make_settings) -> None:
    summary = ProjectIntelligence(make_settings()).generate_summary()
    assert summary["total_claims"] == 0


def test_placeholder_detectors_return_empty(make_settings) -> None:
    engine = ProjectIntelligence(make_settings())
    engine.add_claim("Fact", ["ev-1"])
    assert engine.detect_stale() == []
    assert engine.detect_conflicts() == []


def test_evidence_claim_defaults() -> None:
    claim = EvidenceClaim("id", "text", ["ev-1"])
    assert claim.confidence == 1.0
    assert claim.is_inference is False
    assert claim.is_uncertain is False


def test_factory_returns_engine(make_settings) -> None:
    assert isinstance(create_intelligence(make_settings()), ProjectIntelligence)
