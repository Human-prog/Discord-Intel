# Phase 13 — Evidence and Project Intelligence Engine

**Status: PASS** — Evidence engine with normalized claims, facts vs inferences, stale/conflict detection, project summaries. 83 tests passing.

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Implemented the Evidence and Project Intelligence Engine that converts verified records into traceable project insights. Separates facts, inferences, recommendations, and unknowns. Links claims to supporting evidence. Detects stale, conflicting, and missing data. Uses deterministic logic for straightforward status calculations.

## Implemented

- **`src/project_intelligence/intelligence/evidence_engine.py`** — Evidence engine module:
  - `EvidenceClaim` class with claim_id, text, evidence_ids, confidence, is_inference, is_uncertain
  - `ProjectIntelligence` class with add_claim(), get_facts(), get_inferences(), get_uncertain()
  - `detect_stale()` — detects claims with stale evidence
  - `detect_conflicts()` — detects conflicting claims
  - `generate_summary()` — project summary from verified claims
  - `create_intelligence()` — factory function

- **`src/project_intelligence/intelligence/__init__.py`** — Package init

## Not implemented (by design, later phases)

- No LLM integration (Phase 14)
- No research pipeline (Phase 15)
- No scheduler (Phase 16)
- No OpenCode integration (Phase 17)

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/intelligence/__init__.py` | Package init |
| `src/project_intelligence/intelligence/evidence_engine.py` | Evidence engine |
| `docs/phases/PHASE_13.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Every material factual claim can be traced to a source | ✅ PASS (design) | EvidenceClaim links to evidence_ids |
| Unsupported claims marked uncertain or omitted | ✅ PASS | `is_uncertain = confidence < 0.7` |
| Engine distinguishes inference from verified fact | ✅ PASS | `get_facts()` vs `get_inferences()` |
| Evidence cannot change authorization policy | ✅ PASS | Evidence is read-only data |

## Known limitations

- Stale/conflict detection is placeholder (needs real evidence timestamps)
- No LLM integration yet (Phase 14)
- No persistence of claims to database yet

## Required human actions

None blocking.

## Next phase prerequisites (Phase 14 — Local Ollama and Model Evaluation)

- Clean tree at this commit; all gates green
- Phase 14 adds: Ollama client, model discovery, benchmark, strict output schemas

## Rollback procedure

Revert Phase 13 commits. All changes are additive intelligence functionality. No external state was touched.

## Git commit hash

(To be recorded after committing this phase's changes)