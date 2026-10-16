# Architecture — Discord Project Intelligence

**Status:** Phase 3 (2026-10-16) — planned architecture plus the verified foundation built so far (configuration, security utilities, quality pipeline). Modules are created incrementally per the roadmap (`docs/ROADMAP.md`). This document is updated as phases complete. Requirements source: `docs/MASTER_SPEC.md`.

## 1. Approach

Modular monolith in Python — a small number of clearly separated modules inside one application, deployed as a few isolated processes (bot, dashboard, worker). No distributed microservice architecture unless measurements demonstrate the need.

## 2. Planned components and responsibilities

| Component | Responsibility | Required access |
|---|---|---|
| Discord adapter | Slash command registration, interaction validation, command routing, safe response formatting | Discord credential; authorized project metadata only |
| Authorization service | Central policy check: user/guild/channel/thread IDs, project ID, capability, feature enablement, read vs. mutating | Reads policy configuration; no external credentials |
| Project router | Map guild/channel (and approved threads) to exactly one project record | Project mapping store (read); writes only via owner-authorized mapping commands |
| GitHub adapter | Read-only retrieval of repository metadata, commits, issues, PRs, releases, CI results | GitHub App installation token (read-only, scoped repos) |
| Research pipeline | Search, retrieve, normalize, deduplicate, score, report external sources | Outbound network (validated URLs only); research provider credential |
| Local model adapter | Ollama calls, schema-validated structured outputs, evidence-only fallback | Loopback Ollama endpoint only; minimized, redacted evidence |
| OpenCode adapter | Future controlled agent tasks — disabled by default, read-only first | Scoped worktree only; no application secrets |
| Scheduler | Due health checks, cache refreshes, scheduled reports | Job-scoped permissions only |
| Storage layer | SQLite access via repository methods, migrations, transactions | Data directory only |
| Monitoring API | Health/status endpoints for the dashboard | Read-only dashboard data |
| Dashboard | Private mobile-friendly status UI | Session secret; read-only data; never Discord/GitHub tokens |
| Security utilities | Redaction, URL validation, audit events, rate limits, input validation | None (pure logic) |

## 3. Planned repository layout

Created incrementally; no empty placeholder modules. Documented deviations noted in §7.

```text
discord-project-intelligence/
├── README.md
├── pyproject.toml
├── .gitignore, .gitattributes, .env.example
├── src/project_intelligence/
│   ├── main.py, config.py, logging_config.py, health.py
│   ├── bot/           # Discord client, commands, authorization glue, channel router
│   ├── dashboard/     # FastAPI app, routes, auth, schemas, templates
│   ├── github/        # read-only client and per-resource retrievers
│   ├── research/      # providers, search, retrieval, normalize, dedup, scoring, reports
│   ├── ai/            # ollama client, prompts, schemas, evidence
│   ├── projects/      # models, context, status, roadmap, recommendations
│   ├── agents/        # opencode client, permissions, task runner, result parser
│   ├── jobs/          # scheduler, queue, worker
│   ├── storage/       # database, migrations, repositories
│   └── security/      # permissions, redaction, audit, url_validation, rate_limits
├── tests/             # unit, integration, security, fixtures
├── docs/              # specs, security, operations, phase reports
├── scripts/           # health_check, register_commands, verify_deployment, backup
└── deploy/            # systemd units (created in Phase 9)
```

## 4. Target stack (versions pinned at implementation time)

| Area | Choice | Notes |
|---|---|---|
| Language | Python 3.12+ | 3.12.10 verified on dev machine; host version to verify when online |
| Discord | discord.py 2.x | Minimal intents; no Message Content intent by default |
| Dashboard | FastAPI + Uvicorn | Loopback bind; no dev-mode/API docs in production |
| Config/validation | Pydantic v2 + pydantic-settings | Fail-closed startup validation |
| HTTP | httpx | Async, explicit timeouts, bounded retries |
| Persistence | SQLite (async-safe access layer) | Versioned migrations; tested backups |
| AI | Ollama HTTP API | Loopback only; schema-validated outputs |
| Tests | pytest (+ async support) | Mocked externals; fixtures for malicious inputs; 100% branch coverage, `fail_under` gate at 95% |
| Quality | Ruff (lint + format), mypy (pydantic plugin), pip-audit, in-repo secret scanner | All enforced in CI (`.github/workflows/ci.yml`, Phase 3) |
| CI | GitHub Actions | Least-privilege workflow permissions (`contents: read`); installs from `requirements.lock` |
| Deployment | systemd on Ubuntu | Docker only if it materially improves isolation |
| Remote access | Tailscale Serve (never Funnel) | Dashboard only; preserve existing OpenCode route |

Version-choice debt resolved (Phases 2–3): venv + editable install with third-party pins in `requirements.lock` (pip freeze); CI installs exactly those pins plus `pip install --no-deps -e .`. No `uv` and no global installs required.

## 5. Process isolation model

| Process | Runs as | Can read | Cannot |
|---|---|---|---|
| Discord bot | Dedicated non-root user | Discord token; authorized project data | Dashboard sessions; GitHub key material beyond its scope |
| Dashboard API | Dedicated non-root user | Read-only dashboard data; session secret | Discord/GitHub tokens; job execution |
| Scheduler/worker | Dedicated non-root user | Job-scoped data | Interactive sessions; unrelated services |
| OpenCode worker (future, disabled) | Dedicated identity/container | Scoped worktree only | Application secrets; host control; other repos |
| Ollama | Existing service | Local models | Public network exposure |

Where SQLite cannot provide a clean read-only dashboard path, a narrow read-only API is exposed between processes instead of granting the dashboard broad database or credential access (decided in Phases 4/7).

## 6. Data flows

- **Project-status request:** authorized Discord user → authorization check → channel→project mapping → approved evidence retrieval (GitHub/local) → evidence summary → optional local Ollama analysis → schema-validated response → authorized output (ephemeral by default).
- **Research request:** authorized request → input validation → privacy sanitization → provider searches → safe retrieval (SSRF-controlled) → normalized records → dedup/scoring → local analysis → report with citations and verification limitations.
- **Dashboard request:** authorized device → Tailscale Serve → loopback-bound dashboard → application authentication → read-only data → response.
- **Future OpenCode request (disabled):** authorized user → job validation → owner approval gate → isolated worker with scoped worktree → captured results → verification → audit log → user review.

Retrieved web/GitHub/Discord content and model output are untrusted data in every flow and can never bypass the authorization service.

## 7. Decisions and deviations log

| Date | Decision | Rationale |
|---|---|---|
| 2026-10-15 | Local folder retains owner-chosen name `Discord Project Intelligence` (spaces) | Owner selected the existing folder; git/Python tooling handles it; documented deviation from the clean-name convention |
| 2026-10-15 | GitHub remote is `Human-prog/Discord-Intel` (not `discord-project-intelligence`) | Owner-created private repo; working name retained for docs |
| 2026-10-15 | Docker not assumed on the homelab | Host offline at bootstrap; systemd-first deployment per spec; Docker only if it materially improves isolation (Phase 9 inspection) |
| 2026-10-15 | Dependency/lock tooling deferred to Phases 2–3 | `uv` absent on dev machine; choose isolated tooling without global installs |
| 2026-10-15 | Configuration is environment-first (env vars + optional `.env`); no YAML settings file | Single validation path and no extra dependency; `.env` is the protected-file mechanism; the `config/` example file from the spec tree is intentionally omitted |
| 2026-10-15 | Dependency tooling resolved: venv + editable install; third-party pins in `requirements.lock` (pip freeze output) | Standard library tooling without `uv`; Phase 3 CI will verify Linux reproducibility |
| 2026-10-15 | Loopback-only enforcement for dashboard bind host and Ollama base URL is part of config validation | Makes the network boundary a tested property, not a convention |
| 2026-10-15 | `diagnostics.py` provides secret-free summaries for the CLI now, health endpoints later | One redaction-safe code path reused by later phases |
| 2026-10-16 | Secret scanning is an in-repo deterministic scanner (`security/secret_scan.py`, `scripts/scan_secrets.py`) instead of gitleaks | Offline, no extra toolchain, reports file/line/rule only (never matched values); tests enforce the repository and its fixtures stay scanner-clean; runs locally and in CI |
| 2026-10-16 | Coverage gate `fail_under = 95` while actual coverage is 100% branch | Small buffer for platform-specific branches in later phases without weakening the gate |
| 2026-10-16 | mypy requires full annotations in `src/` and `scripts/`; test functions may omit signatures (bodies still checked) | pytest fixture/parameter conventions; keeps type safety where it matters most |
| 2026-10-16 | CI installs from `requirements.lock` + `pip install --no-deps -e .`; pip upgraded before audit | Reproducible installs without resolver drift; pip-audit reports only real dependency findings |

## 8. Trust boundaries (summary; expanded in `docs/THREAT_MODEL.md`, Phase 5)

1. Internet → host: blocked by design except outbound-initiated TLS connections.
2. Tailnet → dashboard: network access is necessary but not sufficient; application authentication always required.
3. Discord → bot: interactions are untrusted input; authorization enforced server-side before any project data access.
4. External content (web/GitHub/issues/READMEs) → models/UI: untrusted data; never instructions; schema-validated and escaped.
5. Models → application: output is untrusted input; validated against schemas and policies.
6. Application → host: no arbitrary command execution anywhere in the initial release.
