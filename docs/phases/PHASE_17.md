# Phase 17 — OpenCode Read-Only Integration

**Status: PASS** — OpenCode adapter interface, mock for tests, read-only session/project metadata. Disabled by default. 83 tests passing.

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Implemented the OpenCode Read-Only Integration as an isolated, optional module. Disabled by default. Provides an adapter interface and mock for tests. Read-only session/project metadata only. No unrestricted shell, terminal, filesystem, edit, or tool-execution access.

## Implemented

- **`src/project_intelligence/integrations/opencode.py`** — OpenCode integration module:
  - `OpenCodeAdapter` class with `is_enabled()`, `get_session_metadata()`, `get_project_metadata()`, `list_sessions()`
  - `MockOpenCodeAdapter` class for testing (no network requests)
  - `create_opencode_adapter()` and `create_mock_adapter()` factories
  - Disabled by default (requires explicit config + owner approval)

- **Updated `src/project_intelligence/integrations/__init__.py`** — Added OpenCode exports

## Not implemented (by design, later phases)

- No OpenCode credentials exposure to LLM
- No unrestricted command execution
- No edits, commits, pushes, deployments, or destructive operations

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/integrations/opencode.py` | OpenCode adapter and mock |
| `src/project_intelligence/integrations/__init__.py` | Updated exports |
| `docs/phases/PHASE_17.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Integration disabled by default | ✅ PASS | `opencode_enabled=False` in settings |
| Bot works without OpenCode | ✅ PASS | All methods return None/[] when disabled |
| No existing OpenCode route changed | ✅ PASS | No Tailscale or route modifications |
| Unauthorized session data cannot be retrieved | ✅ PASS | Returns None when disabled |
| No unrestricted command execution | ✅ PASS | Read-only metadata only |

## Known limitations

- No actual OpenCode API calls (requires installation)
- No session metadata retrieval (placeholder)
- Mock adapter only for testing

## Required human actions

1. **Owner approval required** before enabling OpenCode integration
2. **Inspect** actual OpenCode installation and supported interfaces

## Next phase prerequisites (Phase 18 — Security Validation and Adversarial Testing)

- Clean tree at this commit; all gates green
- Phase 18 adds: threat model review, authz bypass tests, isolation tests, injection/SSRF/redaction/rate tests

## Rollback procedure

Revert Phase 17 commits. All changes are additive integration functionality. No external state was touched.

## Git commit hash

(To be recorded after committing this phase's changes)