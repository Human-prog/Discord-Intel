# Discord Project Intelligence

Private, self-hosted project-intelligence system for a personal Ubuntu homelab. Discord slash commands, a private mobile-first read-only dashboard, read-only GitHub evidence, local Ollama analysis, and a controlled research pipeline — with strict authorization, evidence-backed reporting, and no public exposure.

> **Current status: Phases 1–20 complete; catalog and research extension deployed (2026-10-23).**
> 515 tests with a 95% branch-coverage gate, plus Ruff, mypy, pip-audit, and a deterministic secret scanner in CI. The dashboard and Discord bot run as hardened systemd services; the dashboard is loopback-bound at `127.0.0.1:8765` and published only on the tailnet via Tailscale Serve. The catalog covers 29 workstation projects and 99 work items; local research is live, and web research is opt-in. Live GitHub, Ollama, and OpenCode integrations remain off by default.

## Repository identity

| Item | Value |
|---|---|
| Working name | `discord-project-intelligence` |
| GitHub remote (`origin`) | `https://github.com/Human-prog/Discord-Intel` (private) |
| Local development path | `C:\Users\Arega\Desktop\Projects\Discord Project Intelligence` |
| Deployment target | Ubuntu homelab `home3013` — LAN `192.168.1.186`, tailnet `100.72.17.90`, service account `dpi` |
| Dashboard | `http://127.0.0.1:8765` on the host; `https://home3013.tail53635c.ts.net` on the tailnet |

## Security posture (project non-negotiables)

- **Read-only release**: the application cannot modify code, run arbitrary commands, or control the host.
- **Private by design**: no public exposure — no port forwarding, no Tailscale Funnel, no public reverse proxy, no inbound webhooks. Remote access is Tailscale Serve plus application authentication, loopback-bound.
- **Fail closed**: missing or ambiguous authorization information is always denied.
- **Secrets never committed**: `.env.example` contains placeholders only; real configuration lives outside the repository with restricted permissions.
- **Untrusted by default**: web pages, GitHub content, Discord content, and AI output are data — never instructions.
- **No autonomous escalation**: OpenCode/agent execution is disabled by default and gated behind explicit approval.

## What exists today

- **Storage** (`src/project_intelligence/storage/`): SQLite connection/transaction layer, versioned migrations (`001_initial`, `002_schema_constraints`, `003_catalog_and_research`), repositories for projects, catalog imports, work items, sources, mappings, users, notes, milestones, evidence, repository snapshots, research jobs/sources/reports, scheduled jobs, health snapshots, and audit events.
- **Security**: centralized authentication/authorization, project and guild/channel scoping, sliding-window rate limits, redaction rules, deterministic secret scanning, path-traversal guards, and audit logging.
- **Health engine**: read-only Git checks constrained to approved roots, explicit `healthy`/`stale`/`unhealthy`/`unknown` states, and persisted snapshots with freshness.
- **Dashboard** (`dashboard/`): FastAPI read-only API plus a single-file mobile UI (dark/light, safe-area aware, sign-in, Projects and Research tabs, project list/detail, catalog summary, milestones, evidence, work history, research list/detail with cited sources, recent activity). Hash routes (`#project-<id>`, `#research-<id>`) survive refresh and mobile back/forward. Owner sessions are stateless HMAC-signed cookies derived from `DASHBOARD_SESSION_SECRET_FILE`; cookies are `HttpOnly`, `SameSite=Strict`, `Secure` in production, expire after 30 days, and are accepted only for `GET`/`HEAD` requests.
- **Discord** (`discord/`): minimal-intent bot with `/help`, `/status`, `/next`, `/roadmap`, `/blocker`, `/connect-project`, `/create-project`, `/note`, `/health`, and `/research`; central authorization, ephemeral replies, idempotent mappings, rate limiting, offline interaction doubles, and a `python -m project_intelligence.discord` runner for the systemd unit.
- **Catalog** (`scripts/catalog_projects.py`, `scripts/import_catalog.py`): read-only workstation scanner for Git repos and manifests, portable JSON over Taildrop, idempotent server import, category/priority detection, and junction deduplication by resolved real path.
- **Research** (`research/`): local keyword search over catalog projects, work items, notes, and prior research with stable citations; optional Tavily/Brave web search behind an SSRF-safe fetcher with DNS/IP validation, manual redirects, response-size limits, HTTPS-in-production, and citation-shaped reports. Jobs persist before work starts, so failures are visible in the dashboard.
- **Jobs**: persistent scheduler with idempotent enqueueing, bounded retries, and backoff.
- **Operations**: hardened systemd units, AppArmor profile, backup/restore script, and deployment/catalog runbook.
- **Quality**: 515 tests (95% branch-coverage gate), Ruff lint/format, strict mypy for `src/`, pip-audit, secret scan, and least-privilege CI.

## Dashboard and mobile access

The dashboard is served from the homelab and is never exposed publicly:

- Local health check: `curl http://127.0.0.1:8765/health`
- Tailnet URL: `https://home3013.tail53635c.ts.net` (Tailscale Serve → `127.0.0.1:8765`)
- Sign in with the owner session secret stored at `/etc/dpi/session_secret` (mode `0640`, `root:dpi`).
- Use the **Projects** tab for catalog status, technology, work history, and recent research; use **Research** for cited reports and source details.
- Discord `/research` links to the dashboard at `DASHBOARD_PUBLIC_URL#research-<job_id>`; set that variable to the tailnet URL, never a public one.
- Rotate the secret by replacing that file and restarting the service; existing sessions are invalidated immediately.
- Do **not** enable Tailscale Funnel, port forwarding, or a public listener. The existing OpenCode Serve route must be preserved.

## Development prerequisites

- Python 3.12+ (development machine currently has 3.12.10; the server runs 3.14.4)
- Git
- No host access required for local development; deployment requires the homelab

## Development setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"     # versions pinned by requirements.lock
.venv\Scripts\python -m pytest -q --cov              # 515 tests + 95% branch-coverage gate
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\python -m mypy .
.venv\Scripts\pip-audit.exe --progress-spinner off
.venv\Scripts\python scripts\scan_secrets.py
.venv\Scripts\python scripts\validate_config.py      # non-destructive configuration check
```

See `CONTRIBUTING.md` for the full gate list and `docs/SECURITY.md` for security rules.

On Linux, use `.venv/bin/python` instead. Configuration is environment-based; copy `.env.example` to `.env` (git-ignored) for local overrides. Real secrets never belong in the repository, and diagnostics never print them.

## Documentation

| Document | Purpose |
|---|---|
| `docs/MASTER_SPEC.md` | Authoritative requirements |
| `docs/ROADMAP.md` | 20-phase plan, status, gates, approval requirements |
| `docs/ARCHITECTURE.md` | Module architecture, trust boundaries, stack |
| `docs/OPERATIONS.md` | Environment inventory, deployment, runbooks, rollback |
| `docs/DISCORD_SETUP.md` | Discord application, bot service, allowlists, first project |
| `docs/IN_DEPTH_REPORT.md` | Consolidated engineering and readiness report |
| `docs/phases/PHASE_01.md` … `PHASE_20.md` | Per-phase implementation and verification reports |
| `docs/SECURITY.md` | Security rules, secret scanning, exposure response procedure |
| `docs/BACKUP_RECOVERY.md` | Backup, restore, and recovery procedures |
| `CONTRIBUTING.md` | Ground rules, development setup, quality gates |
| `deploy/` | systemd unit, AppArmor profile, backup tooling |
