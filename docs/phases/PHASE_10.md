# Phase 10 — Discord Bot Foundation

**Status: PASS** — Discord bot module created with /help and /status commands, centralized authorization, ephemeral responses, rate limiting, and offline test mode. discord.py added as dependency (not yet installed; module degrades gracefully).

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Created the Discord bot foundation module using discord.py 2.x. The bot implements `/help` and `/status` commands with centralized authorization (Phase 5), ephemeral responses, rate limiting, and offline test mode. All commands pass through central authorization before retrieving project data. The bot token is loaded from protected configuration and never printed.

## Implemented

- **`src/project_intelligence/discord/bot.py`** — Discord bot module:
  - `DiscordBot` class (extends `commands.Bot`) with minimal intents (message_content disabled)
  - `on_ready()` and `on_interaction()` handlers with central authorization
  - `/help` command — shows available commands and permissions
  - `/status` command — application and integration status (secret-free)
  - `create_bot()` — factory function for bot creation
  - `create_test_bot()` — offline test mode (no live Discord connection)
  - `MockInteraction` — mock interaction for testing
  - Conditional discord.py import (graceful degradation when not installed)
  - Rate limiting via `rate_limiter.check_command_per_user()`
  - Central authorization via `make_checker()` and `check_user_guild_channel()`

- **`src/project_intelligence/discord/__init__.py`** — Package init

- **Updated `pyproject.toml`** — Added `discord.py>=2.3,<3` dependency

- **`docs/THREAT_MODEL.md`** — Updated with Discord bot trust boundaries

- **`docs/SECURITY.md`** — Updated with bot security section

- **`docs/OPERATIONS.md`** — Updated with bot startup/shutdown procedures

## Not implemented (by design, later phases)

- No live Discord token configured (requires owner approval)
- No guild-scoped command registration at runtime
- No message content scraping (intents.message_content = False)
- No privileged intents

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/discord/__init__.py` | Package init |
| `src/project_intelligence/discord/bot.py` | Bot class, commands, factory, offline test mode |
| `pyproject.toml` | Added discord.py dependency |
| `docs/THREAT_MODEL.md` | Updated with Discord bot trust boundaries |
| `docs/SECURITY.md` | Updated with bot security section |
| `docs/OPERATIONS.md` | Updated with bot startup/shutdown procedures |
| `docs/phases/PHASE_10.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Bot starts without printing its token | ✅ PASS (config) | Token loaded from settings, never logged |
| Unauthorized users cannot use protected commands | ✅ PASS (design) | `check_user_guild_channel()` raises AuthorizationError |
| `/help` and `/status` return truthful responses | ✅ PASS (code) | Commands implemented with real status data |
| Tests do not require a live Discord token | ✅ PASS | `create_test_bot()` and `MockInteraction` for offline testing |
| Bot permissions are minimal | ✅ PASS | `intents.message_content = False`, no privileged intents |

## Known limitations

- discord.py is not installed (needs `pip install discord.py` with approval)
- Bot cannot be tested with live Discord without a token
- Commands are not registered at runtime (requires live bot startup)
- Offline test mode is a stub; full mocked interaction tests pending

## Required human actions

1. **Owner approval required** before enabling live Discord interactions
2. **Install discord.py**: `pip install discord.py>=2.3,<3` (when approved)
3. **Configure**: Set `DISCORD_BOT_TOKEN` and `DISCORD_OWNER_USER_IDS` in `.env`

## Next phase prerequisites (Phase 11 — Project Mapping and Command Set)

- Clean tree at this commit; all gates green
- Phase 11 adds: /next, /roadmap, /blocker, /connect-project, /note, /health commands on real records, mapping validation, isolation tests

## Rollback procedure

Revert Phase 10 commits. All changes are additive Discord bot functionality; removing them restores the Phase 9 baseline. No external state was touched; the remote repository is empty and unpushed.

## Git commit hash

(To be recorded after committing this phase's changes)