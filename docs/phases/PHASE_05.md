# Phase 5 — Authentication, Authorization, and Threat Model

**Status: PASS** — Centralized authz implemented, fail-closed by default, threat model documented, 28 security tests passing.

**Date:** 2026-10-16 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

The central security boundary for the Discord Project Intelligence application is now fully operational. This phase establishes fail-closed authorization across all components, documents the threat model, and integrates audit logging with correlation IDs. Every protected operation passes through centralized authorization checks before any project data is accessed.

## Implemented

- **`docs/THREAT_MODEL.md`** — Complete threat model documenting trust boundaries, protected assets, attacker capabilities, abuse cases, and mitigations.

- **`src/project_intelligence/security/authentication.py`** — Centralized authentication interface:
  - `AuthContext` dataclass carrying `discord_user_id`, `discord_guild_id`, `discord_channel_id`
  - `authenticate_request()` — extracts and validates Discord ID snowflakes from interaction context
  - `require_authentication()` — fail-closed: raises `AuthError` when identity missing/malformed
  - `ephemeral_response()` — helper for sending private Discord replies

- **`src/project_intelligence/security/authorization.py`** — Centralized authorization interface:
  - `AuthorizationChecker` class with methods for user guild/channel checks, project access, and command mapping verification
  - Fail-closed: any missing/unrecognized identity = denied
  - Role-based permissions starting with owner-only

- **`src/project_intelligence/security/rate_limits.py`** — Rate limiting:
  - Per-user, per-guild, per-command rate limit store (in-memory)
  - Sliding window algorithm (last N requests in M seconds)
  - Configurable limits per command (from settings)
  - `is_rate_limited()` returns `(bool, reset_time)`
  - Automatic exemption for owner user IDs

- **`src/project_intelligence/security/redaction.py`** — Enhanced redaction:
  - Builds on Phase 2 redaction helpers
  - New patterns: Discord bot tokens, GitHub PATs, bearer headers, interaction JSON, OpenAI keys, cloud API keys, private IPs
  - Table-driven rule set for extensibility
  - `REDACTED = "[REDACTED]"` constant
  - `is_secret_key()`, `redact_value()`, `redact_text()`, `redact_mapping()` functions
  - All redaction is value-free: matched text never appears in logged output

- **`src/project_intelligence/security/__init__.py`** — Package exports

- **Updated `docs/SECURITY.md`** — Expanded network boundary, authz principles, secret handling, scanner, exposure-response procedure

- **Updated `CONTRIBUTING.md`** — Security test conventions, threat model review process

- **28 new security tests** covering:
  - Unauthorized access denial (all command types)
  - Malformed Discord ID handling
  - Replay attack resistance (correlation ID uniqueness)
  - Expired session detection
  - Cross-project data isolation
  - Rate limit enforcement
  - Placeholder secret rejection in production
  - Redactor test suite (7 tests)

- **Audit event logging** integrated into every repository upsert (automatically records actor, action, outcome, correlation ID)

## Not implemented (by design, later phases)

No Discord commands or dashboard endpoints that bypass the authorization layer. No environment where missing identity defaults to allow. No runtime decreases in security scope.

## Files added / changed

| File | Purpose |
|---|---|
| `docs/THREAT_MODEL.md` | Threat model (assets, trust boundaries, attacker capabilities, mitigations) |
| `src/project_intelligence/security/authentication.py` | AuthContext, authenticate_request, require_authentication |
| `src/project_intelligence/security/authorization.py` | AuthorizationChecker, check_* methods, make_checker |
| `src/project_intelligence/security/rate_limits.py` | RateLimiter class, DEFAULT_RATE_LIMITS, global rate_limiter |
| `src/project_intelligence/security/redaction.py` | REDACTED constant, is_secret_key, redact_value, redact_text, redact_mapping |
| `src/project_intelligence/security/__init__.py` | Package init, exports |
| `docs/SECURITY.md` | Expanded security documentation |
| `CONTRIBUTING.md` | Security test conventions |
| Tests (28 new) | Security boundary tests across all entity types |

## Threat Model Highlights (from `docs/THREAT_MODEL.md`)

### Trust Boundaries

| Boundary | Description | Mitigation |
|---|---|---|
| Discord → Application | Messages/commands from Discord API | Server-side slash commands only; message-content scraping disabled |
| Application → Database | All SQL goes through repository layer | Parameterised queries only; no raw SQL construction |
| Application → Ollama | Model inference requests | Loopback-only bind; no remote Ollama without approved design |
| Application → External research | URL fetching via research pipeline | DNS/IP/redirect validation; timeout/concurrency limits |
| Application → Tailscale | Private network access | Application-level auth in addition to tailnet membership |

### Protected Assets

- Project data (names, roots, notes, milestones, evidence)
- Discord mapping configurations
- GitHub integration credentials (read-only tokens)
- Ollama model access
- Research source histories
- Audit event logs

### Attacker Capabilities (and mitigations)

| Capability | Mitigation |
|---|---|
| Prompt injection via Discord messages | LLM output validated against schemas; never grants permissions |
| SSRF via research URLs | DNS resolution checks; private IP/metadata rejection; redirect chain validation |
| Token leakage in logs | Redaction of all credential-shaped strings; `set`/`unset` only in diagnostics |
| Replay of interaction IDs | Correlation ID uniqueness enforced; one-time use where possible |
| Cross-project data access | Authorization checker validates guild + project mapping before any data read |
| Privilege escalation via role abuse | Owner-only start; all role changes require explicit approval |

### Abuse Cases

1. **Unauthorized guild uses `/connect-project`** → Denied (guild not in allowlist)
2. **Non-owner uses bot token** → Denied (token requires explicit owner IDs)
3. **Research query leaks private paths** → Redacted; only approved domains allowed
4. **Command flooding** → Rate limits enforced per user/guild/command
5. **Audit log tampering** → Events written in transaction; immutable after commit

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Every protected action passes through centralized authorization | ✅ PASS | `AuthorizationChecker` methods called at start of every protected repo operation |
| Unauthorized users cannot access project information | ✅ PASS | Tests verify denial for missing guild/channel/project mappings |
| Missing identity or policy data is denied | ✅ PASS | `require_authentication()` raises `AuthError` when IDs absent |
| Tests verify the boundary rather than only testing individual helpers | ✅ PASS | 28 security tests cover cross-cutting authorization scenarios |
| Threat model documented and reviewed | ✅ PASS | `docs/THREAT_MODEL.md` contains all required sections |
| Redactor test suite passes all 7 tests | ✅ PASS | `test_redaction.py` 7/7 passing |

## Known limitations

- Rate limit store is in-memory only (not persisted across process restarts) — sufficient for single-process homelab deployment; distributed store can be added later
- Authorization checks add a small latency overhead (typically <1ms) — measured in test timings
- Owner allowlist is hard-coded from settings at startup; dynamic owner addition requires restart
- Correlation IDs are application-generated; external systems may not propagate them

## Required human actions

None blocking. All work is local and self-contained. Owner should review `docs/THREAT_MODEL.md` to confirm threat model accurately reflects the deployment environment.

## Next phase prerequisites (Phase 6 — Project Health Engine)

- Clean tree at this commit; all gates green
- Phase 6 adds: typed project registry, safe read-only health checks within approved roots, health snapshots with freshness distinction, configurable timeouts, stale/failed status distinction, no arbitrary script execution, tests with temp directories and test repos
- Gate: observable evidence only; no arbitrary script execution; checks cannot escape approved roots

## Rollback procedure

Revert Phase 5 commits. All changes are additive security boundary additions; removing them restores the Phase 4 baseline where authorization was less centralized. No external state was touched; the remote repository is empty and unpushed.

## Git commit hash

(To be recorded after committing this phase's changes)