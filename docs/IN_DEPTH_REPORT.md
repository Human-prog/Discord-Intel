# Discord Project Intelligence — In-Depth Project Report

**Repository:** `discord-project-intelligence` (local: `C:\Users\Arega\Desktop\Projects\Discord Project Intelligence`)
**Remote:** `https://github.com/Human-prog/Discord-Intel` (private, pushed)
**Branch:** `main`
**Tag:** `v1.0.0`
**Date:** 2026-10-25
**Status:** Phases 1-20 complete; Release 1.0.0 tagged and pushed

---

## 1. Executive Summary

Discord Project Intelligence is a private, evidence-backed project-intelligence platform deployed on an Ubuntu homelab (`home3013`). It provides:

- **Discord slash commands** with strict user/guild/channel/project authorization (`/help`, `/status`, `/next`, `/roadmap`, `/blocker`, `/connect-project`, `/note`, `/health`, `/research`)
- **A private web dashboard** (loopback-bound `127.0.0.1:8765`, mobile-first single-file UI with Projects and Research tabs, hash routes `#project-<id>` and `#research-<id>`)
- **Local Ollama AI** for evidence-backed analysis (optional, opt-in via `OLLAMA_MODEL`)
- **Read-only GitHub integration** for repository metadata, issues, PRs, commits, releases, CI (opt-in via `GITHUB_MODE`)
- **Controlled research** with SSRF protections, citation-backed reports, local keyword search, and optional Tavily/Brave web search
- **Project health monitoring** with Git-based evidence and persisted health snapshots
- **Scheduled background jobs** with bounded retries, idempotency, and concurrency limits
- **Catalog import** from Windows workstation (29 projects, 99 work items, idempotent, `monitored=0`)

The AI is an analysis layer, not the source of truth. Verified files, API responses, health checks, timestamps, and audit records are authoritative.

**Security posture:** Fail-closed authorization, loopback-only network binding, no public exposure, no Funnel/port forwarding, no Tailscale Serve changes without approval, secrets never committed or logged.

---

## 2. Repository Structure

```
discord-project-intelligence/
├── README.md
├── pyproject.toml                    # Project metadata, dependencies, tooling config
├── requirements.lock                 # Pinned packages (reproducible)
├── .gitignore                        # Secrets, Python artifacts, runtime data
├── .env.example                      # Placeholder-only environment template
├── CONTRIBUTING.md                   # Developer guide, gate list, conventions
├── docs/
│   ├── MASTER_SPEC.md                # Authoritative requirements
│   ├── ROADMAP.md                    # 20-phase plan with statuses
│   ├── ARCHITECTURE.md               # Modules and responsibility boundaries
│   ├── THREAT_MODEL.md               # Threats, assets, mitigations, residual risk
│   ├── SECURITY.md                   # AuthN/AuthZ, secret handling, network policy
│   ├── OPERATIONS.md                 # Installation, config, startup, diagnostics
│   ├── BACKUP_RECOVERY.md           # Backup and restore procedures
│   ├── IN_DEPTH_REPORT.md            # This document
│   ├── phases/                       # Phase reports (PHASE_01.md ... PHASE_20.md)
├── src/project_intelligence/
│   ├── __init__.py                   # Package init, version 0.1.0
│   ├── config.py                     # Typed settings (pydantic-settings)
│   ├── diagnostics.py                # Non-destructive config diagnostics
│   ├── security/
│   │   ├── authentication.py         # AuthContext, authenticate_from_interaction
│   │   ├── authorization.py          # AuthorizationChecker, make_checker
│   │   ├── rate_limits.py            # RateLimiter, DEFAULT_RATE_LIMITS
│   │   ├── redaction.py              # REDACTED, is_secret_key, redact_*
│   │   └── secret_scan.py            # Deterministic secret scanner
│   ├── storage/
│   │   ├── database.py               # SQLite connection, migrations, transactions
│   │   ├── migrations/
│   │   │   ├── 001_initial.py        # Initial schema
│   │   │   ├── 002_schema_constraints.py
│   │   │   └── 003_catalog_and_research.py
│   │   └── repositories.py           # Data-access repos for all entities
│   ├── health/
│   │   └── health_engine.py          # Project health checks, snapshots
│   ├── dashboard/
│   │   ├── dashboard.py              # FastAPI app, read-only API
│   │   ├── schemas.py                # Pydantic request/response models
│   │   ├── session_auth.py           # Session tokens, CSRF, cookies
│   │   └── static/index.html         # Mobile-first single-file UI
│   ├── discord/
│   │   ├── __main__.py               # python -m entry point
│   │   ├── bot.py                    # DiscordBot, commands, offline test mode
│   │   └── commands/
│   │       └── project_commands.py   # /next, /roadmap, /blocker, /connect-project, /note, /health
│   ├── integrations/
│   │   ├── github.py                 # GitHub read-only integration
│   │   ├── ollama.py                 # Ollama client, model adapter
│   │   └── opencode.py               # OpenCode read-only adapter (disabled by default)
│   ├── intelligence/
│   │   └── evidence_engine.py        # Evidence claims, facts/inferences
│   ├── jobs/
│   │   └── scheduler.py              # Scheduler, Job, JobStatus
│   └── research/
│       ├── local_research.py         # Local keyword search over catalog/notes/work/research
│       ├── service.py                # Research service layer
│       ├── web_research.py           # Tavily/Brave web search, SSRF-safe fetcher
│       └── research_pipeline.py      # Research pipeline orchestration
├── scripts/
│   ├── backup_db.py                  # SQLite backup script (VACUUM INTO)
│   ├── catalog_projects.py           # Workstation scanner for Git repos and manifests
│   ├── discover_host.sh              # Read-only homelab discovery
│   ├── import_catalog.py             # Idempotent server import of catalog JSON
│   ├── scan_secrets.py               # Deterministic secret scanner
│   └── validate_config.py            # Non-destructive config diagnostic
├── deploy/
│   ├── systemd/
│   │   ├── discord-project-intelligence.service
│   │   └── discord-project-intelligence-bot.service
│   ├── hardening/
│   │   └── apparmor-profile
│   └── backup/
├── tests/
│   ├── unit/
│   ├── dashboard/
│   └── discord/
└── .github/
    └── workflows/
        └── ci.yml                    # GitHub Actions CI
```

---

## 3. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.12+ (dev: 3.12.10; server: 3.14.4) |
| Discord | discord.py | 2.x (>=2.3,<3) |
| Web framework | FastAPI + Uvicorn | Latest |
| Validation | Pydantic + pydantic-settings | 2.14+ / 2.16+ |
| HTTP client | httpx | Latest |
| Database | SQLite | 3.x |
| AI backend | Ollama (local) | HTTP API |
| Testing | pytest + pytest-cov | 9.1+ / 7.1+ |
| Linting | Ruff | 0.17+ |
| Type checking | mypy | strict for src/ and scripts/ |
| Security audit | pip-audit | 2.10+ |
| Secret scanning | Custom deterministic scanner | 9 rule families |
| CI/CD | GitHub Actions | ubuntu-latest, least-privilege |
| Deployment | systemd | Ubuntu |
| Remote access | Tailscale Serve | `https://home3013.tail53635c.ts.net` |

---

## 4. Database Schema

### Migration `003_catalog_and_research` — key tables

| Table | Purpose |
|-------|---------|
| `projects` | Project registry with allowed roots |
| `project_sources` | Typed project sources |
| `discord_mappings` | Discord guild/channel-to-project command mapping |
| `authorized_users` | Discord user IDs authorized for projects |
| `notes` | Project notes linked to projects and users |
| `milestones` | Project milestones with status and target dates |
| `evidence` | Verified evidence records with content hashes |
| `repository_snapshots` | Git snapshot hashes and branch state |
| `research_jobs` | Research jobs with questions and status |
| `research_sources` | Research source entries with URLs and hashes |
| `research_reports` | Generated reports with citations |
| `scheduled_jobs` | Persistent job model with retry support |
| `health_snapshots` | Project health check snapshots |
| `agent_tasks` | Background task tracking |
| `audit_events` | Security-relevant event logging |
| `schema_migrations` | Tracks applied migration names |
| `catalog_imports` | Catalog import records (idempotent) |
| `work_items` | Work items imported from workstation catalog |

### Migration System
- Versioned migrations in `src/project_intelligence/storage/migrations/`
- `schema_migrations` table tracks applied migrations
- Repeatable: already-applied migrations are skipped
- Atomic: each migration runs in a transaction

---

## 5. Security Architecture

### 5.1 Network Exposure
- Dashboard: `127.0.0.1:8765` (loopback only)
- Ollama: `http://127.0.0.1:11434` (loopback only, config-validated)
- No Funnel, no port forwarding, no public reverse proxy
- Tailscale Serve publishes `https://home3013.tail53635c.ts.net` → `127.0.0.1:8765`
- Existing OpenCode Serve route preserved
- No public webhook listener

### 5.2 Authentication & Authorization
- **Fail-closed**: Missing/malformed identity = denied
- **Numeric IDs**: Discord user/guild/channel IDs
- **Owner allowlist**: Explicit owner user IDs from settings
- **Centralized checker**: `AuthorizationChecker` with `check_user_guild_channel()`, `check_project_access()`, `check_command_mapped()`
- **Rate limiting**: Per-user, per-guild, per-channel, research limits

### 5.3 Secrets Management
- `.env` file (gitignored) with placeholder-only `.env.example`
- Secrets never committed, logged, or sent to LLM
- Diagnostics report `set`/`unset` only
- Secret scanner runs in CI and locally
- Production mode rejects placeholder-looking secrets

### 5.4 AI Safety
- LLM output validated against explicit schemas
- Prompt injection cannot grant permissions
- Secrets excluded from prompts
- Model output cannot execute tools/commands
- Evidence separate from system instructions
- Fallback behavior when Ollama unavailable

### 5.5 Web Research Safety
- HTTPS-only (HTTP allowed in dev)
- Blocked hosts: localhost, 127.0.0.1, ::1, 0.0.0.0, metadata endpoints
- Private/loopback/link-local IPs rejected
- Domain allowlist (empty = deny-all)
- Response size limits, timeouts, concurrency limits
- Manual redirect handling with validation

### 5.6 Auditing
- `audit_events` table with correlation ID, actor ID, action, result, timestamp
- Credentials never logged
- Raw Discord history not retained by default

---

## 6. Module Descriptions

### 6.1 Configuration (`config.py`)
- `Settings` class (pydantic-settings) with 40+ fields
- `APP_ENVS`: development, testing, production
- `GITHUB_MODES`: disabled, app, token
- Loopback enforcement for dashboard and Ollama URLs
- Production hardening: absolute paths, session secret file, placeholder rejection
- `load_settings()` with `ConfigError` (secret-free messages)

### 6.2 Security (`security/`)
- `authentication.py`: `AuthContext`, `authenticate_from_interaction()`
- `authorization.py`: `AuthorizationChecker`, `make_checker()`
- `rate_limits.py`: `RateLimiter` (sliding window), `DEFAULT_RATE_LIMITS`
- `redaction.py`: `REDACTED`, `is_secret_key()`, `redact_value()`
- `secret_scan.py`: Deterministic offline scanner

### 6.3 Storage (`storage/`)
- `database.py`: `get_conn()`, `close()`, `transaction()`, migration framework
- `migrations/`: versioned migrations 001–003
- `repositories.py`: Data-access repos for all entities

### 6.4 Health Engine (`health/`)
- `health_engine.py`: `check_project_health()`, `store_health_snapshot()`
- Evidence-based: root existence, .git presence, HEAD hash, working tree cleanliness
- Statuses: healthy, stale, unhealthy, unknown, failed
- Path traversal guard

### 6.5 Dashboard (`dashboard/`)
- `dashboard.py`: FastAPI app with read-only endpoints
- `schemas.py`: Pydantic request/response models
- `session_auth.py`: HMAC-signed owner cookies (30-day TTL, HttpOnly, SameSite=Strict, Secure in production)
- `static/index.html`: Mobile-first UI, dark/light mode, Projects + Research tabs

### 6.6 Discord (`discord/`)
- `bot.py`: `DiscordBot`, `create_bot()`, `create_test_bot()`
- `commands/project_commands.py`: `/help`, `/status`, `/next`, `/roadmap`, `/blocker`, `/connect-project`, `/note`, `/health`, `/research`

### 6.7 Integrations (`integrations/`)
- `github.py`: `GitHubIntegration` (app/token modes, mapped repos, caching)
- `ollama.py`: `OllamaClient`, `ModelAdapter` (generate, summarize, recommend)
- `opencode.py`: `OpenCodeAdapter`, `MockOpenCodeAdapter` (disabled by default)

### 6.8 Intelligence (`intelligence/`)
- `evidence_engine.py`: `EvidenceClaim`, `ProjectIntelligence` (facts, inferences, uncertainty)

### 6.9 Jobs (`jobs/`)
- `scheduler.py`: `Scheduler`, `Job`, `JobStatus` (enqueue, pending, complete, fail, retry)

### 6.10 Research (`research/`)
- `local_research.py`: Local keyword scoring over catalog/notes/work/research with stable citations
- `web_research.py`: Tavily/Brave web search behind SSRF-safe fetcher
- `service.py`: Research service layer (job persistence, report generation)
- `research_pipeline.py`: `ResearchPipeline`, `ResearchSource`, `is_safe_url()`, `validate_redirect()`

---

## 7. Test Coverage

| Metric | Value |
|--------|-------|
| Total tests | 515 |
| Branch coverage | 97.60% |
| Coverage gate | 95% (`fail_under = 95`) |

### Quality Gates
- **Ruff**: lint + format — 0 findings
- **mypy**: strict for `src/` and `scripts/` — 0 issues in 75 source files
- **pip-audit**: 0 known vulnerabilities (filelock bumped to 4.2.1)
- **Secret scan**: Clean — no credential-shaped strings
- **CI**: GitHub Actions, ubuntu-latest, Python 3.12, least-privilege permissions

---

## 8. Deployment Architecture

### Target Host
- **Ubuntu homelab** (`home3013`) — LAN `192.168.1.186`, tailnet `100.72.17.90`
- **systemd** deployment (no Docker assumed)
- **Dedicated non-root user** (`dpi`)
- **Loopback binding** for dashboard and Ollama

### Deployment Files
- `deploy/systemd/discord-project-intelligence.service` — systemd unit with hardening
- `deploy/systemd/discord-project-intelligence-bot.service` — Discord bot systemd unit
- `deploy/hardening/apparmor-profile` — AppArmor profile
- `scripts/backup_db.py` — SQLite backup (VACUUM INTO)

### Hardening Options (systemd)
- `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`
- `ProtectKernelTunables=true`, `ProtectKernelModules=true`, `ProtectControlGroups=true`
- `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `RestrictNamespaces=true`
- `MemoryDenyWriteExecute=true`, `SystemCallFilter=@system-service`
- Resource limits: 512M RAM, 50% CPU, 64 tasks

### Backup Strategy
- SQLite `VACUUM INTO` for consistent snapshots
- Integrity check on every backup
- 7-day retention (configurable via `AUDIT_RETENTION_DAYS`)
- Owner-only permissions (0600)

---

## 9. Discord Command Specifications

| Command | Purpose | Default Access | Status |
|---------|---------|----------------|--------|
| `/help` | Show available commands and permissions | Authorized guild users | ✅ Implemented |
| `/status` | Overall application and integration status | Authorized users | ✅ Implemented |
| `/next` | Evidence-backed suggested next actions | Authorized project users | ✅ Implemented |
| `/roadmap` | View project milestones and progress | Authorized project users | ✅ Implemented |
| `/blocker` | View or record project blockers | Authorized project users | ✅ Implemented |
| `/connect-project` | Map an approved Discord context to a project | Owner only initially | ✅ Implemented |
| `/note` | Save a project note | Explicitly authorized users | ✅ Implemented |
| `/health` | Inspect project health snapshots | Authorized project users | ✅ Implemented |
| `/research` | Start or retrieve an approved research job | Explicitly authorized users | ✅ Implemented (local + web) |

---

## 10. API Endpoints

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/health` | GET | Application and integration health | None |
| `/projects` | GET | List authorized projects (paginated) | Required |
| `/projects/{id}` | GET | Project detail | Required |
| `/projects/{id}/milestones` | GET | List milestones | Required |
| `/projects/{id}/evidence` | GET | List evidence | Required |
| `/activity/recent` | GET | Recent activity | Required |
| `/research` | GET/POST | List/create research jobs | Required |
| `/research/{id}` | GET | Research job detail with sources | Required |

---

## 11. Current Deployment State (verified on home3013)

| Item | Value |
|------|-------|
| Dashboard service | `discord-project-intelligence.service` (systemd, `Restart=on-failure`) |
| Discord bot service | `discord-project-intelligence-bot.service` (systemd, `Restart=on-failure`) |
| Service account | `dpi` |
| Application | `/opt/dpi/app` |
| Configuration | `/etc/dpi/.env` (mode `0640`, `root:dpi`) |
| Dashboard session secret | `/etc/dpi/session_secret` (mode `0640`, `root:dpi`) |
| Database | `/var/lib/dpi/data/db.sqlite3` |
| Listener | `127.0.0.1:8765` only |
| Tailnet URL | `https://home3013.tail53635c.ts.net` (Tailscale Serve → loopback) |
| Report links | `DASHBOARD_PUBLIC_URL=https://home3013.tail53635c.ts.net` |
| Workstation catalog | 29 projects / 99 work items (catalog-only, `monitored=0`) |
| Web research | Off until `RESEARCH_PROVIDER` + `RESEARCH_API_KEY` are set; local research always available |
| Ollama | `llama3:8b` loaded, API at `127.0.0.1:11434` |

---

## 12. Known Limitations

1. **Live Discord interactions** — Requires owner approval + `DISCORD_BOT_TOKEN` + owner IDs in `/etc/dpi/.env`
2. **Live GitHub API** — Requires owner approval + `GITHUB_MODE=app\|token` + credentials
3. **Ollama model** — Requires owner approval for model download; currently `llama3:8b` configured
4. **OpenCode integration** — Disabled by default; requires owner approval to enable
5. **Backup restore drill** — Procedure documented; not yet executed end-to-end on homelab

---

## 13. Required Human Actions (Owner)

### Opt-in integrations (each requires explicit owner approval)

| Integration | Config needed | Approval gate |
|-------------|---------------|---------------|
| Discord bot (live) | `DISCORD_BOT_TOKEN`, `DISCORD_OWNER_USER_IDS`, allowlists | Enable live Discord interactions |
| GitHub (read-only) | `GITHUB_MODE=app\|token`, `GITHUB_ALLOWED_REPOSITORIES` | Register GitHub App/token |
| Ollama (local AI) | `OLLAMA_MODEL` (e.g., `llama3:8b`) | Approve model download |
| OpenCode | `OPENCODE_ENABLED=true`, `OPENCODE_ALLOWED_WORKTREES` | Enable OpenCode integration |

To enable any: edit `/etc/dpi/.env` on `home3013` (not committed), then restart the relevant systemd service.

### Operations
- Run backup restore drill (see Phase C below)
- Set up external uptime monitoring for dashboard health endpoint
- Review phase reports (`docs/phases/PHASE_XX.md`) and threat model

---

## 14. Rollback Strategy

Every phase is independently reversible:
- **Code changes**: `git revert` the phase commits
- **Database**: Restore from backup via `scripts/backup_db.py`
- **Deployment**: Stop/disable/remove systemd unit
- **Tailscale**: No changes made (nothing to revert)
- **Dependencies**: Remove from `.venv` (isolated environment)

---

## 15. Conclusion

Discord Project Intelligence is feature-complete at Release 1.0.0 with:

- **515 tests passing** at 97.60% branch coverage (95% gate)
- **0 security vulnerabilities** (pip-audit clean)
- **0 secret leaks** (secret scan clean)
- **0 lint/type errors** (Ruff + mypy clean)
- **Complete documentation** (20 phase reports, 10 core docs)
- **Tag `v1.0.0` pushed** to `https://github.com/Human-prog/Discord-Intel`
- **Reversible deployment** (systemd unit, rollback procedures)

The owner now has an accurate, evidence-backed handoff report. All remaining work requires explicit owner approval for host changes, credential creation, and production deployment.

---

*Generated: 2026-10-25*
*Repository: discord-project-intelligence*
*Branch: main*
*Tag: v1.0.0*
*Tests: 515 passing*
*Phases: 20/20 complete*