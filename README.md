# Discord Project Intelligence

Private, self-hosted project-intelligence system for a personal Ubuntu homelab. Planned capabilities: Discord slash commands, a private mobile-friendly read-only dashboard, read-only GitHub evidence, local Ollama analysis, and a controlled research pipeline — with strict authorization, evidence-backed reporting, and no public network exposure.

> **Current status: Phase 2 of 20 complete — configuration foundation.**
> Typed, fail-closed configuration with secure defaults, redaction helpers, and a non-destructive diagnostics command — all unit-tested. The system does not connect to Discord or GitHub, run background jobs, or serve a dashboard yet.

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
| `docs/phases/PHASE_01.md` | Phase 1 implementation and verification report |
| `scripts/discover_host.sh` | Read-only homelab discovery script (run when the host is online) |

## Development prerequisites

- Python 3.12+ (development machine currently has 3.12.10)
- Git
- No host access required for Phases 2–7; the homelab is needed from the deployment/Tailscale phases onward

## What exists today

- Repository scaffold and documentation set.
- Typed configuration (`src/project_intelligence/config.py`) with fail-closed validation: loopback-only dashboard and Ollama, deny-by-default allowlists, production hardening.
- Redaction helpers (`src/project_intelligence/security/redaction.py`) and a non-destructive configuration check (`scripts/validate_config.py`).
- Unit tests (59) covering valid, invalid, missing, and conflicting settings.
- Read-only host-discovery script (`scripts/discover_host.sh`) for the homelab.

## Development setup (Phase 2+)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"     # versions pinned by requirements.lock
.venv\Scripts\python -m pytest                      # run the test suite
.venv\Scripts\python scripts\validate_config.py     # non-destructive configuration check
```

On Linux, use `.venv/bin/python` instead. Configuration is environment-based; copy `.env.example` to `.env` (git-ignored) for local overrides. Real secrets never belong in the repository, and diagnostics never print them.
