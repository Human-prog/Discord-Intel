# Discord Project Intelligence

Private, self-hosted project-intelligence system for a personal Ubuntu homelab. Planned capabilities: Discord slash commands, a private mobile-friendly read-only dashboard, read-only GitHub evidence, local Ollama analysis, and a controlled research pipeline — with strict authorization, evidence-backed reporting, and no public network exposure.

> **Current status: Phase 1 of 20 complete — repository bootstrap only.**
> No application code exists yet. Nothing here runs, connects to Discord or GitHub, or serves a dashboard. Features described in the documentation are planned, not implemented.

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

- Repository scaffold, documentation set, and a read-only host-discovery script.
- Nothing to install, build, or run yet. Phase 2 adds validated configuration and secure defaults.
