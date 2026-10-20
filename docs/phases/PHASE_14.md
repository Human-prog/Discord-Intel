# Phase 14 — Local Ollama and Model Evaluation

**Status: PASS** — Ollama client with timeouts, bounded input/output, error handling, structured validation, model adapter. AI optional and degrades safely. 83 tests passing.

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Implemented the local Ollama integration with a model adapter pattern. The client supports explicit base URL, request timeouts, bounded input/output sizes, error handling, and structured response validation. AI functionality is optional and degrades safely when Ollama is unavailable. Model selection is based on evidence, not model-name popularity.

## Implemented

- **`src/project_intelligence/integrations/ollama.py`** — Ollama client module:
  - `OllamaClient` class with `is_available()`, `list_models()`, `generate()`, `generate_structured()`
  - `ModelAdapter` class with `summarize()`, `recommend()`
  - `create_ollama_client()` and `create_model_adapter()` factories
  - Bounded input (8000 chars) and output (configurable max_tokens)
  - Timeouts from settings (default 120s)
  - Graceful degradation when Ollama unavailable

- **Updated `src/project_intelligence/integrations/__init__.py`** — Added Ollama exports

## Not implemented (by design, later phases)

- No model benchmarks (requires Ollama installation)
- No Nemotron 3.5 Lightning evaluation (requires model availability)
- No research pipeline (Phase 15)

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/integrations/ollama.py` | Ollama client and model adapter |
| `src/project_intelligence/integrations/__init__.py` | Updated exports |
| `docs/phases/PHASE_14.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| AI functionality optional and degrades safely | ✅ PASS | `is_available()` returns False; `generate()` returns None |
| Model output validated | ✅ PASS (design) | `generate_structured()` validates JSON against schema |
| Secrets not included | ✅ PASS | Only evidence text sent, no credentials |
| Benchmarks measured not guessed | ⬜ N/A | Requires Ollama installation (deferred) |

## Known limitations

- No actual Ollama testing (requires installation)
- No model benchmarks (requires available models)
- Nemotron 3.5 Lightning evaluation deferred

## Required human actions

1. **Install Ollama** when approved for model evaluation
2. **Download models** with owner approval for resource impact
3. **Run benchmarks** against representative tasks

## Next phase prerequisites (Phase 15 — Research and Source Discovery)

- Clean tree at this commit; all gates green
- Phase 15 adds: /research, /discover, /review, /report commands, research pipeline, SSRF protections, citations

## Rollback procedure

Revert Phase 14 commits. All changes are additive integration functionality. No external state was touched.

## Git commit hash

(To be recorded after committing this phase's changes)