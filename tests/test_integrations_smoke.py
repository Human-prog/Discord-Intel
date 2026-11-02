"""Smoke tests for new integrations and commands (Phase 28+)."""
from project_intelligence.integrations.github import create_github_integration
from project_intelligence.config import load_settings
from project_intelligence.jobs.scheduler import Scheduler
from project_intelligence.intelligence.evidence_engine import EvidenceClaim


def test_github_integration_imports() -> None:
    gh = create_github_integration(load_settings())
    assert gh is not None


def test_scheduler_imports() -> None:
    sched = Scheduler()
    assert sched is not None


def test_evidence_claim_imports() -> None:
    claim = EvidenceClaim(claim_id="test", text="hello", evidence_ids=[])
    assert claim is not None
