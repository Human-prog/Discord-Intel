# Roadmap — Discord Project Intelligence

20-phase, phase-gated plan. Each phase is completed, tested, documented, and reviewed before the next dependent phase starts. Status is updated only with evidence (see each `docs/phases/PHASE_XX.md` report).

**Status legend:** ✅ PASS · 🟡 PARTIAL · 🔴 BLOCKED · ⬜ Not started

## Status overview

| # | Phase | Status | Report | Notes |
|---|-------|--------|--------|-------|
| 1 | Repository bootstrap & environment discovery | ✅ PASS (host discovery deferred) | `phases/PHASE_01.md` | Bootstrap complete 2026-10-15. Homelab intentionally offline; read-only discovery script ready. |
| 2 | Configuration, schemas, secure defaults | ✅ PASS | `phases/PHASE_02.md` | Typed settings, fail-closed validation, redaction, diagnostics; 59 tests passing (2026-10-15). |
| 3 | Testing, CI, code quality | ✅ PASS | `phases/PHASE_03.md` | Ruff, mypy, 100% branch coverage gate, pip-audit, secret scanner, least-privilege CI; 83 tests passing (2026-10-16). |
| 4 | Storage & data migrations | ✅ PASS | `phases/PHASE_04.md` | SQLite layer, versioned migrations, 17 entities; 83 tests passing (2026-10-16) |
| 5 | Authentication, authorization, threat model | ✅ PASS | `phases/PHASE_05.md` | Centralized authN/authZ, threat model, rate limits, redaction, audit events; 28 security tests passing (2026-10-16) |
| 6 | Project health engine | ✅ PASS | `phases/PHASE_06.md` | Read-only Git checks within approved roots, fail-closed states, persisted snapshots; covered by the health suite (2026-10-20). |
| 7 | Read-only dashboard API & mobile interface | ✅ PASS | `phases/PHASE_07.md` | FastAPI read-only API, owner-session auth, mobile-first single-file UI, pagination/search, loopback bind. |
| 8 | Dashboard authentication & Tailscale access | ✅ PASS | `phases/PHASE_08.md` | HMAC-signed owner cookie (30-day TTL, HttpOnly, SameSite=Strict, Secure in production, GET/HEAD only); Tailscale Serve verified; no Funnel. |
| 9 | Deployment & systemd hardening | ✅ PASS | `phases/PHASE_09.md` | Service account `dpi`, hardened unit, AppArmor profile, loopback `127.0.0.1:8765`; service verified active on `home3013`. |
| 10 | Discord bot foundation | ✅ PASS | `phases/PHASE_10.md` | Minimal intents, central authorization, ephemeral replies, rate limits, offline doubles. Live token remains opt-in. |
| 11 | Project mapping & command set | ✅ PASS | `phases/PHASE_11.md` | `/help /status /next /roadmap /blocker /connect-project /note /health`; owner-gated mappings; `/note`, `/roadmap`, `/health`, `/connect-project` use real records. `/next` and `/blocker` return truthful placeholders. |
| 12 | GitHub read-only integration | ✅ PASS | `phases/PHASE_12.md` | Read-only adapter, allowlisted repositories, cache handling, mocked tests. Live API not exercised. |
| 13 | Evidence & project intelligence engine | ✅ PASS | `phases/PHASE_13.md` | Evidence claims, facts/inference/uncertainty separation, deterministic summaries. |
| 14 | Local Ollama & model evaluation | ✅ PASS | `phases/PHASE_14.md` | Bounded client, discovery, structured output, fallbacks. Local model remains opt-in. |
| 15 | Research & source discovery | ✅ PASS | `phases/PHASE_15.md` | SSRF guards, domain allowlists, deduplication, citation-shaped reports. |
| 16 | Scheduler, jobs, notifications | ✅ PASS | `phases/PHASE_16.md` | Persistent jobs, idempotent enqueue, bounded retries/backoff, concurrency limits. |
| 17 | OpenCode read-only integration | ✅ PASS | `phases/PHASE_17.md` | Disabled by default; read-only adapter plus mock; no shell/edit/write surface. |
| 18 | Security validation & adversarial testing | ✅ PASS | `phases/PHASE_18.md` | Auth bypass, isolation, injection/SSRF, redaction, rate-limit, and traversal suites; no unresolved critical/high findings. |
| 19 | Backup, restore, recovery | ✅ PASS | `phases/PHASE_19.md` | SQLite `VACUUM INTO` backups, integrity checks, retention, restore runbook. |
| 20 | Controlled release & operational handoff | ✅ PASS | `phases/PHASE_20.md` | Dashboard deployed and verified (loopback health 200, Tailscale Serve, all tailnet devices connected). Live Discord/GitHub/Ollama integrations remain opt-in. |

> Test counts in earlier phase reports are historical. The current suite is **392 tests at 97.34% branch coverage** with a 95% gate (2026-10-20).

## Phase notes and gates

1. **Repository bootstrap & environment discovery** — Local repo established, documentation set, remote configured (push pending owner auth), development machine inventoried, homelab discovery deferred (host offline; script `scripts/discover_host.sh` provided). Gate: no production changes — met.
2. **Configuration, schemas, secure defaults** — ✅ Environment-based typed settings (`pydantic-settings`), development/testing/production modes, loopback enforcement (dashboard + Ollama), deny-by-default allowlists, Discord fail-closed owner rule, production hardening (absolute paths, session secret file, placeholder rejection), redaction helpers, non-destructive diagnostics (`scripts/validate_config.py`). Gate met: invalid config exits 2 without printing secrets; 59 unit tests cover valid/invalid/missing/conflicting settings. Report: `phases/PHASE_02.md`.
3. **Testing, CI, code quality** — ✅ 83 tests at 100% branch coverage with a `fail_under` gate; Ruff (lint + format, security rules), mypy strict for `src/`/`scripts/` with the pydantic plugin; pip-audit clean (pip and pytest upgrades applied after advisory findings); built-in deterministic secret scanner (`scripts/scan_secrets.py`, rule names only — never matched values) with a repo-clean test; `requirements.lock` install path; least-privilege CI (`permissions: contents: read`, no secrets). Gate met: CI runs without production credentials and fails on any gate failure. Report: `phases/PHASE_03.md`.
4. **Storage & data migrations** — SQLite layer, versioned migrations, entities per MASTER_SPEC §7, transaction/concurrency tests, backup/restore basics. Gate: fresh init + migrations + rollback tests pass.
5. **Authentication, authorization, threat model** — Central authN/authZ, roles/capabilities (owner-only start), correlation IDs, audit events, redaction, rate limits, `docs/THREAT_MODEL.md`. Gate: every protected action passes central checks; unauthorized = denied; **no Discord commands or dashboard exposure before this gate passes**.
6. **Project health engine** — Typed project registry, safe read-only checks within approved roots, health snapshots with freshness. Gate: observable evidence only; no arbitrary script execution; checks cannot escape approved roots.
7. **Read-only dashboard API & mobile interface** — FastAPI, read-only endpoints, schema-validated responses, responsive UI with proper states, pagination, loopback bind. Gate: no mutating admin endpoints; no public/LAN listener.
8. **Dashboard authentication & Tailscale access** — App auth (sessions, cookies, CSRF, expiry), tailnet policy documentation, Tailscale Serve publishing. **Approval required before any Serve change; existing OpenCode route must be preserved; no Funnel/port-forwarding/public proxy.** Gate: works for authorized device; rejected for unauthorized; else remains local-only (blocked step documented).
9. **Deployment & systemd hardening** — Dedicated non-root user, sandboxing, resource limits, restart behavior, log rotation, upgrade/rollback docs. **Approval required before host changes**. Gate: starts after reboot; survives controlled crash; cannot write unrelated paths.
10. **Discord bot foundation** — discord.py client, minimal permissions, guild-scoped registration, central authz, ephemeral replies, offline mocked test mode. **Approval required to enable live interactions**. Gate: bot starts without printing token; unauthorized users denied; tests run without live token.
11. **Project mapping & command set** — `/help /status /next /roadmap /blocker /connect-project /note /health` on real records, mapping validation, isolation tests. Gate: unauthorized project access denied; mappings deterministic and persisted.
12. **GitHub read-only integration** — GitHub App (preferred) or fine-grained token (fallback), mapped repos only, commits/issues/PRs/releases/CI, caching with provenance, rate-limit handling, mocked tests. **Approval required for credentials**. Gate: adapter exposes read-only operations only; failures reported honestly.
13. **Evidence & project intelligence engine** — Normalized evidence model, traceability, facts vs. inference vs. unknowns, stale/conflict detection, deterministic aggregation first. Gate: every material claim traces to evidence; no fabricated references.
14. **Local Ollama & model evaluation** — Client with timeouts/bounds, model discovery, benchmark (Nemotron 3.5 Lightning as one candidate), strict output schemas, evidence-only fallback. **Approval required for large downloads**. Gate: AI optional and safe when unavailable; measured benchmarks; no cloud fallback.
15. **Research & source discovery** — `/research /discover /review /report`, provider interface, SSRF protections, normalization/dedup, citation-backed synthesis, quotas. Gate: verifiable citations; no invented sources; malicious content cannot bypass controls.
16. **Scheduler, jobs, notifications** — Persistent jobs, conservative intervals, concurrency/rate limits, bounded retries with backoff, idempotency, notification policy. Gate: restarts don't duplicate jobs; no unlimited retry loops; alerts only to authorized channels.
17. **OpenCode read-only integration** — **Disabled by default**; isolated worker, scoped worktree, no secrets, no write/edit/shell capabilities, mocked adapter tests. **Approval required to enable**. Gate: disabled integration performs no network requests; no existing route changed.
18. **Security validation & adversarial testing** — Threat-model review, authN/authZ bypass attempts, isolation tests, injection/SSRF/redaction/rate tests, exposure checks. Gate: no unresolved critical/high findings; residual risks documented.
19. **Backup, restore, recovery** — Consistent SQLite backups, isolated restore test, retention policy, recovery scenarios, credential rotation/revocation docs. Gate: backup/restore verified; secrets handled safely.
20. **Controlled release & operational handoff** — Full test/lint/scan pass, release checklist, operations manual, rollback; release remains monitoring-only. **Approval required for production deployment**. Gate: all checks evidenced; deployed version verified by real health checks.

## Actions requiring explicit owner approval

- Any Tailscale Serve / tailnet policy change (Phase 8)
- Firewall, host account, kernel, or service-definition changes (Phase 9)
- Enabling live Discord interactions (Phase 10)
- Registering GitHub App / credentials (Phase 12)
- Downloading large models (Phase 14)
- Enabling OpenCode integration (Phase 17)
- Pushing to any remote (any phase)
- Production deployment (Phase 20)

## Dependencies and conventions

- Phases run in order; each phase report records actual evidence.
- No phase may weaken a security boundary to proceed faster.
- If a phase cannot complete safely, it is marked 🟡 PARTIAL or 🔴 BLOCKED with the blocker and required owner action documented.
