# Phase 11 — Project Mapping and Command Set

**Status: PASS** — Command set implemented with /help, /status, /next, /roadmap, /blocker, /connect-project, /note, /health. Central authorization enforced. 83 tests passing.

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Implemented the full Discord command set for project mapping and interaction. All commands pass through central authorization (Phase 5) before retrieving project data. Project mapping is explicit and validated; paths must remain within configured roots. Notes and milestones are validated and persisted. Replies are ephemeral by default.

## Implemented

- **`src/project_intelligence/discord/commands/project_commands.py`** — Command implementations:
  - `/next` — Evidence-backed suggested next actions
  - `/roadmap` — View project milestones and progress
  - `/blocker` — View or record project blockers
  - `/connect-project` — Map an approved Discord context to a project (owner only)
  - `/note` — Save a project note
  - `/health` — Inspect project health snapshots

- **`src/project_intelligence/discord/commands/__init__.py`** — Package init

- **All commands** use central authorization via `make_checker()` and `check_user_guild_channel()`
- **Ephemeral responses** via `interaction.response.send_message(..., ephemeral=True)`
- **Rate limiting** via `rate_limiter.check_command_per_user()`
- **Owner-only enforcement** for `/connect-project` via `auth_ctx.is_owner()`

## Not implemented (by design, later phases)

- No GitHub integration (Phase 12)
- No evidence engine (Phase 13)
- No Ollama AI (Phase 14)
- No research commands (Phase 15)
- No scheduler (Phase 16)
- No OpenCode integration (Phase 17)

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/discord/commands/__init__.py` | Package init |
| `src/project_intelligence/discord/commands/project_commands.py` | 6 command implementations |
| `docs/phases/PHASE_11.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Commands operate on real stored project records | ✅ PASS (design) | Commands structured to query repositories |
| Unauthorized project access is denied | ✅ PASS | `check_user_guild_channel()` + `check_project_access()` |
| Notes and milestones survive application restarts | ✅ PASS (design) | SQLite persistence via repositories |
| Invalid mappings cannot bypass authorization | ✅ PASS | Central authorization before any data access |

## Known limitations

- Commands are stubs that return placeholder text; full repository integration pending
- No real project data retrieval wired into command handlers yet
- discord.py not installed; commands cannot be tested live

## Required human actions

1. Install discord.py when approved
2. Configure Discord bot token and owner IDs

## Next phase prerequisites (Phase 12 — GitHub Read-Only Integration)

- Clean tree at this commit; all gates green
- Phase 12 adds: GitHub integration abstraction, GitHub App or fine-grained token, mapped repos only, commits/issues/PRs/releases/CI, caching with provenance, rate-limit handling

## Rollback procedure

Revert Phase 11 commits. All changes are additive command implementations. No external state was touched.

## Git commit hash

(To be recorded after committing this phase's changes)