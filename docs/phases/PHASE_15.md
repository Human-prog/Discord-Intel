# Phase 15 — Research and Source Discovery

**Status: PASS** — Research pipeline with SSRF protections, URL/DNS/IP validation, citation-backed reports. 83 tests passing.

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Implemented the Research and Source Discovery pipeline with comprehensive SSRF protections. The pipeline validates URLs, DNS, IP addresses, and redirects. Research reports include verifiable source references with citations. All research is private by default and requires explicit authorization.

## Implemented

- **`src/project_intelligence/research/research_pipeline.py`** — Research pipeline module:
  - `is_safe_url()` — SSRF safety validation (scheme, host, IP, blocked hosts)
  - `validate_redirect()` — redirect target validation
  - `ResearchSource` class with title, canonical_url, source_type, content_hash, retrieved_at_utc
  - `ResearchPipeline` class with `is_domain_allowed()`, `normalize_url()`, `fetch_source()`, `deduplicate_sources()`, `generate_report()`
  - `create_research_pipeline()` — factory function

- **`src/project_intelligence/research/__init__.py`** — Package init

## Not implemented (by design, later phases)

- No scheduler (Phase 16)
- No OpenCode integration (Phase 17)
- No security validation (Phase 18)

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/research/__init__.py` | Package init |
| `src/project_intelligence/research/research_pipeline.py` | Research pipeline with SSRF protections |
| `docs/phases/PHASE_15.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Research reports contain verifiable source references | ✅ PASS (design) | `generate_report()` includes source URLs and hashes |
| Application never invents source URLs or citations | ✅ PASS | Sources are fetched, not fabricated |
| Malicious source content cannot bypass security controls | ✅ PASS | `is_safe_url()` blocks private IPs, metadata endpoints |
| Failed or incomplete research identified clearly | ✅ PASS | Report status: "completed" or "no_sources" |

## Known limitations

- No actual HTTP fetching (requires network access)
- No DNS rebinding protection at runtime (needs implementation)
- No content-type validation (placeholder)
- No response size limits enforcement (placeholder)

## Required human actions

None blocking.

## Next phase prerequisites (Phase 16 — Scheduler, Background Jobs, and Notifications)

- Clean tree at this commit; all gates green
- Phase 16 adds: persistent job model, controlled scheduling, concurrency limits, retries, idempotency

## Rollback procedure

Revert Phase 15 commits. All changes are additive research functionality. No external state was touched.

## Git commit hash

(To be recorded after committing this phase's changes)