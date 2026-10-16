# Discord Project Intelligence

Private, self-hosted project-intelligence system for a personal Ubuntu homelab. Planned capabilities: Discord slash commands, a private mobile-friendly read-only dashboard, read-only GitHub evidence, local Ollama analysis, and a controlled research pipeline — with strict authorization, evidence-backed reporting, and no public network exposure.

> **Current status: Phase 3 of 20 complete — testing, CI, and code quality.**
> Typed, fail-closed configuration (Phase 2) plus the full quality pipeline: 83 tests at 100% branch coverage, Ruff, mypy, pip-audit, a built-in secret scanner, and a least-privilege GitHub Actions workflow. The system does not connect to Discord or GitHub, run background jobs, or serve a dashboard yet.

## Repository identity

| Item | Value |
|---|---|
| Working name | `discord-project-intelligence` |
| GitHub remote (`origin`) | `https://github.com/Human-prog/Discord-Intel` — private, currently empty; first push pending owner authentication |
| Local development path | `C:\Users\Arega\Desktop\Projects\Discord Project Intelligence` |
| Deployment target | Ubuntu homelab `homelab3013` (currently powered off; discovery deferred — see `docs/OPERATIONS.md`) |

## Security posture (project non-negotiables)

- **Read-only release**: the initial release cannot modify code, run arbitrary commands, or control the host.
- **Private by design**: no public exposure — no port forwarding, no Tailscale Funnel, no public reverse proxy, no inbound webhooks. Future remote access: Tailscale Serve + application authentication, loopback-bound.
- **Fail closed**: missing or ambiguous authorization information is always denied.
- **Secrets never committed**: `.env.example` contains placeholders only; real configuration lives outside the repository with restricted permissions.
- **Untrusted by default**: web pages, GitHub content, Discord content, and AI output are data — never instructions.
- **No autonomous escalation**: OpenCode/agent execution is disabled by default and gated behind explicit approval phases.

## Documentation

| Document | Purpose |
|---|---|
| `docs/MASTER_SPEC.md` | Authoritative requirements |
| `docs/ROADMAP.md` | 20-phase plan, status, gates, approval requirements |
| `docs/ARCHITECTURE.md` | Planned module architecture, trust boundaries, stack |
| `docs/OPERATIONS.md` | Environment inventory, host discovery, runbooks, rollback |
| `docs/phases/PHASE_02.md` | Phase 2 implementation and verification report |
| `docs/phases/PHASE_03.md` | Phase 3 implementation and verification report |
| `docs/SECURITY.md` | Security rules, secret scanning, exposure response procedure |
| `CONTRIBUTING.md` | Ground rules, development setup, quality gates |
| `scripts/discover_host.sh` | Read-only homelab discovery script (run when the host is online) |

## Development prerequisites

- Python 3.12+ (development machine currently has 3.12.10)
- Git
- No host access required for Phases 2–7; the homelab is needed from the deployment/Tailscale phases onward

## What exists today

- Repository scaffold and documentation set.
- Typed configuration (`src/project_intelligence/config.py`) with fail-closed validation: loopback-only dashboard and Ollama, deny-by-default allowlists, production hardening.
- Redaction helpers (`src/project_intelligence/security/redaction.py`), a deterministic secret scanner (`src/project_intelligence/security/secret_scan.py` + `scripts/scan_secrets.py`), and a non-destructive configuration check (`scripts/validate_config.py`).
- 83 unit/security tests at 100% branch coverage, enforced by a coverage gate.
- Quality pipeline: Ruff (lint + format), mypy (with pydantic plugin), pip-audit, secret scan — all wired into `.github/workflows/ci.yml` (least-privilege, no secrets).
- Read-only host-discovery script (`scripts/discover_host.sh`) for the homelab.

## Development setup (Phase 2+)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"     # versions pinned by requirements.lock
.venv\Scripts\python -m pytest --cov                 # tests + coverage gate
.venv\Scripts\ruff check .; .venv\Scripts\ruff format --check .
.venv\Scripts\python -m mypy .
.venv\Scripts\pip-audit --progress-spinner off
.venv\Scripts\python scripts\scan_secrets.py
.venv\Scripts\python scripts\validate_config.py      # non-destructive configuration check
```

See `CONTRIBUTING.md` for the full gate list and `docs/SECURITY.md` for security rules.

On Linux, use `.venv/bin/python` instead. Configuration is environment-based; copy `.env.example` to `.env` (git-ignored) for local overrides. Real secrets never belong in the repository, and diagnostics never print them.
