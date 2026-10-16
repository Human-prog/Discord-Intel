# Phase 2 — Configuration, Schemas, and Secure Defaults

**Status: PASS.**
**Date:** 2026-10-15 · **Branch:** `main` · **Phase commit:** `3388007` (code, tests, lockfile), followed by a docs commit containing this report.

## Implementation summary

Implemented the typed configuration foundation using `pydantic-settings`: settings load from environment variables and an optional `.env` file, validate fail-closed with secure defaults, and never expose secret values. Added redaction helpers, a secret-free diagnostics module, a non-destructive CLI check, and a 59-test unit suite. No integration is enabled; nothing connects to any network service.

## Implemented

- **`Settings` model** covering all planned areas: application, Discord, GitHub (read-only), Ollama, research, dashboard, projects, jobs/limits, network behavior, OpenCode.
- **Fail-closed rules enforced:**
  - Dashboard bind host and Ollama base URL must be loopback addresses (all modes).
  - `GITHUB_MODE=app|token` requires its credentials; anything else disables GitHub.
  - A Discord bot token without explicit owner user IDs is refused.
  - OpenCode cannot be enabled without an explicit command and scoped worktrees.
  - Missing allowlists (guilds, channels, repositories, domains, worktrees, project roots) are empty = deny-all.
- **Production hardening:** absolute `DATA_DIR`/`DATABASE_PATH` required; `DASHBOARD_SESSION_SECRET_FILE` required; placeholder-looking secrets (`changeme`, `<...>`, `example`, ...) rejected; the offending value is never echoed.
- **Redaction helpers** (`security/redaction.py`): key-based mapping redaction (recursive) and free-text redaction for bearer headers, GitHub token shapes, and `token=...`/`api_key=...` assignments.
- **Diagnostics** (`diagnostics.py`): `summarize_settings` (secrets reported only as `set`/`unset`), `format_summary`, and read-only `check_runtime_prerequisites` (file/command existence; no writes, no network).
- **CLI** (`scripts/validate_config.py`): exit 0 valid, 2 invalid, 3 valid-with-prerequisite-errors; ASCII-safe output.
- **`.env.example`**: exact implemented names with comments; copying it verbatim yields a valid development configuration (covered by a test).
- **Dependencies** (editable install in `.venv`; third-party pins committed in `requirements.lock`): pydantic 2.14.1, pydantic-settings 2.16.0, pytest 8.4.2 (+ transitive deps).

## Not implemented (by design, later phases)

No Discord/GitHub/Ollama/research/dashboard runtime; no database; no logging configuration beyond redaction helpers; no CI, lint, or type checks (Phase 3); no service entry points.

## Files added / changed

- **Added:** `src/project_intelligence/{__init__,config,diagnostics}.py`, `src/project_intelligence/security/{__init__,redaction}.py`, `scripts/validate_config.py`, `tests/conftest.py`, `tests/unit/{test_config,test_redaction,test_diagnostics}.py`, `requirements.lock`
- **Modified:** `pyproject.toml` (build system, dependencies, pytest config), `.env.example`, `README.md`, `docs/{ROADMAP,ARCHITECTURE,OPERATIONS,MASTER_SPEC}.md`

## Commands actually run (with results)

| Command | Result |
|---|---|
| `python -m venv .venv` | venv created on Python 3.12.10 |
| `.venv\Scripts\python -m pip install -e ".[dev]"` | success; pydantic 2.14.1, pydantic-settings 2.16.0, pytest 8.4.2 installed |
| `.venv\Scripts\python -m pytest -q` | **59 passed, 0 failed, 0 skipped** (0.26 s) — run twice, green both times |
| `.venv\Scripts\python scripts\validate_config.py` | exit 0; secret-free summary; info note: data dir not created yet (non-destructive) |
| `APP_ENV=bad` + validate_config | exit 2; error lists allowed values; the invalid value itself is not echoed |
| `APP_ENV=production` + validate_config | exit 2 (relative `DATA_DIR` refused) — fail-safe demonstrated |
| `pip freeze` (filtered to third-party) | `requirements.lock`: 13 pinned packages |
| Secret-pattern scan (8 credential patterns; excludes `.git`, `.venv`, caches) | CLEAN. First run flagged only gitignored `__pycache__` binary artifacts of a test file; caches were deleted and token fixtures rewritten programmatically so the scan stays clean by construction |

## Test counts

59 total: config 46 (including parametrized cases), redaction 7, diagnostics 6. Failures: 0. Skipped: 0. Errors: 0.

## Security checks performed

- Secret scan CLEAN before commit (patterns: GitHub PATs, Discord token shape, AWS keys, PEM private keys, `sk-` keys, generic `token/secret/api_key=...` assignments).
- Diagnostics proven secret-free by test: raw secret values are asserted absent from summary text; `set`/`unset` markers only.
- Validation-error rendering proven not to echo secret values (placeholder-rejection test asserts the raw value is absent from the rendered error).
- Loopback enforcement tested for dashboard bind host and Ollama URL — non-loopback rejected in every mode, including production.
- No `.env` file exists; no real secret exists anywhere in the repository; `.gitignore` covers `.env*`, keys, databases, logs.
- No host, network, firewall, or service changes; packages installed only inside `.venv`.

## Acceptance criteria (Phase 2)

| Criterion | Result | Evidence |
|---|---|---|
| Invalid configuration fails safely | PASS | CLI exits 2 with a secret-free message; `ConfigError` wraps `ValidationError`; unit tests |
| Secret values never appear in diagnostic output | PASS | `set`/`unset` only; tests assert raw values absent from output and errors |
| Production startup cannot silently use insecure defaults | PASS | relative paths, missing session-secret file, and placeholders all rejected; tests |
| Unit tests cover valid, invalid, missing, and conflicting settings | PASS | 59 tests across three suites |

## Known limitations

- Lint/format/type checks not configured yet (Phase 3).
- `requirements.lock` was generated on Windows; Linux reproducibility is verified in Phase 3 CI.
- `check_runtime_prerequisites` covers an initial small set of checks; later phases extend it.
- Dashboard default port is 8765 (owner may change before Phase 7 — no impact).

## Required human actions

None blocking.

## Next phase prerequisites (Phase 3 — Testing, CI, Code Quality)

- Clean tree at this commit; reproducible venv via `pip install -e ".[dev]"`.
- Phase 3 adds: pytest configuration polish, Ruff, type checking, coverage, GitHub Actions CI (runner OS decided there), dependency audit, secret scanning in CI, contributor guide.

## Rollback procedure

`git revert` the Phase 2 commits (all changes are additive; no persisted data exists). Delete `.venv/` locally if desired. No external state was touched.
