# Roadmap — Discord Project Intelligence

20-phase, phase-gated plan. Each phase is completed, tested, documented, and reviewed before the next dependent phase starts. Status is updated only with evidence (see each `docs/phases/PHASE_XX.md` report).

**Status legend:** ✅ PASS · 🟡 PARTIAL · 🔴 BLOCKED · ⬜ Not started

## Status overview

| # | Phase | Status | Report | Notes |
|---|-------|--------|--------|-------|
| 1 | Repository bootstrap & environment discovery | ✅ PASS (host discovery deferred) | `phases/PHASE_01.md` | Bootstrap complete 2026-10-15. Homelab intentionally offline; read-only discovery script ready. |
| 2 | Configuration, schemas, secure defaults | ⬜ Not started | — | Next phase. No host dependency. |
| 3 | Testing, CI, code quality | ⬜ Not started | — | — |
| 4 | Storage & data migrations | ⬜ Not started | — | — |
| 5 | Authentication, authorization, threat model | ⬜ Not started | — | Gate: no Discord commands / dashboard exposure until authz tests pass. |
| 6 | Project health engine | ⬜ Not started | — | — |
| 7 | Read-only dashboard API & mobile interface | ⬜ Not started | — | Loopback bind mandatory. |
| 8 | Dashboard authentication & Tailscale access | ⬜ Not started | — | **Owner approval required** for Tailscale Serve changes. |
| 9 | Deployment & systemd hardening | ⬜ Not started | — | **Owner approval required** for host changes. |
| 10 | Discord bot foundation | ⬜ Not started | — | **Owner approval required** to enable live Discord interactions. |
| 11 | Project mapping & command set | ⬜ Not started | — | — |
| 12 | GitHub read-only integration | ⬜ Not started | — | **Owner approval required** for credentials/App registration. |
| 13 | Evidence & project intelligence engine | ⬜ Not started | — | — |
| 14 | Local Ollama & model evaluation | ⬜ Not started | — | **Owner approval required** for large model downloads. |
| 15 | Research & source discovery | ⬜ Not started | — | — |
| 16 | Scheduler, jobs, notifications | ⬜ Not started | — | — |
| 17 | OpenCode read-only integration | ⬜ Not started | — | Disabled by default; **owner approval required** to enable. |
| 18 | Security validation & adversarial testing | ⬜ Not started | — | Release-blocking gate for critical/high findings. |
| 19 | Backup, restore, recovery | ⬜ Not started | — | — |
| 20 | Controlled release & operational handoff | ⬜ Not started | — | **Owner approval required** for production deployment. |

## Phase notes and gates

1. **Repository bootstrap & environment discovery** — Local repo established, documentation set, remote configured (push pending owner auth), development machine inventoried, homelab discovery deferred (host offline; script `scripts/discover_host.sh` provided). Gate: no production changes — met.
2. **Configuration, schemas, secure defaults** — Typed settings, dev/test/prod modes, fail-safe validation, redaction, deny-by-default. Gate: invalid config fails safely; no secrets in diagnostics; unit tests for valid/invalid/missing/conflicting settings.
3. **Testing, CI, code quality** — pytest + fixtures, Ruff, type checks, lockfile, GitHub Actions, dependency audit, secret scanning. Gate: CI runs without production credentials; failures block.
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
