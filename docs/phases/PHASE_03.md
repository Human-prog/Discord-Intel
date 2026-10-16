# Phase 3 — Testing, CI, and Code Quality

**Status: PASS** — one tracked pending item: the CI workflow's first remote execution happens on the first push (owner action; see *Required human actions*).
**Date:** 2026-10-16 · **Branch:** `main` · **Phase commit:** `b46a47b` (code, tooling, CI), followed by a docs commit containing this report.

## Implementation summary

The repository now has a full, enforced quality pipeline: Ruff (lint + format, security rules), mypy (pydantic plugin; strict for `src/` and `scripts/`), pytest with a branch-coverage gate, pip-audit, and a built-in deterministic secret scanner. All gates also run in a least-privilege GitHub Actions workflow that installs exactly the pinned `requirements.lock`. The test suite grew from 59 to 83 tests and runs at 100% branch coverage. Two dependency advisories found by pip-audit were fixed by upgrading pip and pytest.

## Implemented

- **Ruff** (`pyproject.toml`): line length 100; rules `E F W I UP B S SIM C4 DTZ RUF`; first-party import detection; test-only per-file ignores (`S101`, `S104`, `S105`, `S106`) with a comment explaining that tests deliberately use non-loopback bind values and credential-shaped strings as rejected inputs. Formatting is enforced (`ruff format --check` in CI).
- **mypy**: `pydantic.mypy` plugin; `disallow_untyped_defs` and related strictness for `src/` and `scripts/`; a `tests.*` override permits untyped test signatures (pytest convention) while function bodies remain type-checked. `tests/` was made a proper package (`tests/__init__.py`, `tests/unit/__init__.py`, `tests/security/__init__.py`) so module resolution is deterministic.
- **Coverage**: branch coverage over `project_intelligence`, `fail_under = 95` (actual: 100%), `show_missing`, exclusions limited to `if TYPE_CHECKING:` and `if __name__ == "__main__":`.
- **New tests** (24 added; 83 total):
  - config: blank `DATA_DIR`, `None` ID list, zero/negative IDs, wrong types for list fields, explicit absolute `DATABASE_PATH`, production relative `DATABASE_PATH` (these closed all previously uncovered branches);
  - diagnostics: existing data dir produces no warning, configured-but-missing session secret file is an error;
  - scanner: 16 tests in `tests/security/test_scan_secrets.py`.
- **Secret scanner (in-repo, replaces gitleaks)**:
  - `src/project_intelligence/security/secret_scan.py` — deterministic, offline; 9 rule families (GitHub PAT/token prefixes, Discord bot token shape, Slack, AWS access keys, PEM private-key headers, OpenAI-style keys, bearer headers, generic `token/secret/password/api_key` assignments); excluded dirs (`.git`, `.venv`, caches, build output, `node_modules`, ...); exact-name `.env` exclusion (real secrets live there by design; everything committed is scanned); binary detection; 20 MB size guard; findings carry file, line, and rule only — **never the matched value**.
  - `scripts/scan_secrets.py` — CLI, exit 0 clean / 1 findings / 2 usage error; ASCII output; repo-root scan is the default.
  - Test fixtures construct credential-shaped strings programmatically; `test_repository_tree_is_clean` asserts the working tree itself stays scanner-clean.
- **CI** (`.github/workflows/ci.yml`): `ubuntu-latest`, Python 3.12, `permissions: contents: read`, concurrency cancel-in-progress, pip cache keyed on `requirements.lock`; installs `-r requirements.lock` + `pip install --no-deps -e .`; runs tests+coverage, `ruff check` + `ruff format --check`, mypy, `pip-audit`, and the secret scan. No secrets are configured or required.
- **Docs**: `CONTRIBUTING.md` (ground rules, setup, gate list, test/secret-fixture conventions), `docs/SECURITY.md` (network boundary, authz principles, secret handling, scanner, exposure-response procedure, supply chain); README/ROADMAP/ARCHITECTURE/OPERATIONS updated.
- **Dependency upgrades after advisories**: pip 25.0.1 -> 26.2.1, pytest 8.4.2 -> 9.1.1 (PYSEC-2026-1845); `requirements.lock` regenerated: 46 pins including the dev toolchain (ruff 0.17.1, mypy 2.4.0, pytest-cov 7.1.0, coverage 7.16.2, pip-audit 2.10.1). pip 26 renders the local editable install via the git origin URL in `pip freeze`; the project line is excluded from the lock and the project is installed with `--no-deps -e .` (verified: install metadata is local, `direct_url.json` = the local folder).

## Not implemented (by design, later phases)

No storage, authz, health engine, dashboard, bot, GitHub, Ollama, or scheduling code. The CI workflow has not executed remotely yet (requires the first push). No mutation of any remote.

## Files added / changed

- **Added:** `src/project_intelligence/security/secret_scan.py`, `scripts/scan_secrets.py`, `tests/security/{__init__,test_scan_secrets}.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `.github/workflows/ci.yml`, `CONTRIBUTING.md`, `docs/SECURITY.md`, `docs/phases/PHASE_03.md`
- **Modified:** `pyproject.toml`, `requirements.lock`, `src/project_intelligence/{config,diagnostics}.py`, `src/project_intelligence/security/{__init__,redaction}.py`, `tests/conftest.py`, `tests/unit/{test_config,test_diagnostics}.py`, `README.md`, `docs/{ROADMAP,ARCHITECTURE,OPERATIONS}.md`

## Commands actually run (with results)

| Command | Result |
|---|---|
| `.venv\Scripts\python -m pip install -e ".[dev]"` | success (mypy, pip-audit, pytest-cov, ruff added) |
| `.venv\Scripts\ruff.exe check .` | first run: 7 findings (3 auto-fixed; SIM102/E501/S104x2 handled) -> **All checks passed!** (exit 0) |
| `.venv\Scripts\ruff.exe format .` | 4 files reformatted total -> **25 files already formatted** (exit 0) |
| `.venv\Scripts\python -m mypy .` | first run: 50 errors (all test-signature policy + conftest generator) -> after strictness override, test packaging, conftest fix: **Success: no issues found in 16 source files** (exit 0) |
| `.venv\Scripts\python -m pytest -q` | **83 passed** (0 failed, 0 skipped) — final run 0.46 s |
| `.venv\Scripts\python -m pytest -q --cov` | **83 passed**; coverage **100.00%** (branch); gate 95% reached |
| `.venv\Scripts\pip-audit.exe --progress-spinner off` | first run: 2 advisories (pip 25.0.1, pytest 8.4.2) -> after upgrades: **No known vulnerabilities found** (exit 0); expected skip notice for the local package |
| `.venv\Scripts\python scripts\scan_secrets.py` | **secret scan clean** (exit 0) |
| `.venv\Scripts\python scripts\validate_config.py` | exit 0, valid configuration (unchanged behavior re-verified) |
| Test counts per file (`--collect-only`) | config 52, diagnostics 8, redaction 7, secret scan 16 = 83 |

## Security checks performed

- Secret scan of the whole working tree: CLEAN, both before commit and as the final gate; the scanner's own tests enforce the repo-clean property going forward.
- Scanner output proven value-free by test: matched text never appears in findings' `repr`/`str` (asserted).
- CI hardening: no secrets referenced; `permissions: contents: read`; no production credentials anywhere in the pipeline.
- pip-audit clean after upgrades; lockfile pins everything CI installs (46 packages, full freeze of runtime + dev toolchain).
- No `.env` file exists; no real secret exists in the repository; `.gitignore` covers `.coverage`, caches, and databases (verified during `git status` review).
- No host, network, firewall, service, or Tailscale changes; packages installed only inside `.venv`.

## Acceptance criteria (Phase 3)

| Criterion | Result | Evidence |
|---|---|---|
| Tests configured and passing with coverage | PASS | 83 passed, 100% branch coverage (Verified, local) |
| Lint and formatting enforced | PASS | `ruff check` and `ruff format --check` clean (Verified, local) |
| Type checks enforced | PASS | mypy: 0 issues in 16 files (Verified, local) |
| Reproducible dependency set | PASS (local) | 46-pin `requirements.lock`; CI installs from it (Linux install verification pending first run) |
| CI runs without production credentials; failures block | PASS (configured) | Workflow reviewed: least privilege, no secrets, all gates fail the job; **first remote execution pending first push** (Reported, not yet Verified) |
| Dependency audit | PASS | pip-audit exit 0, no known vulnerabilities |
| Secret scanning in place and clean | PASS | Scanner + CLI + repo-clean test; final scan CLEAN |
| Contributor documentation | PASS | `CONTRIBUTING.md`, `docs/SECURITY.md` |

## Known limitations

- The CI workflow's first remote execution is pending the first push (owner action); until then, CI behavior is reproduced locally with the exact same commands.
- The scanner is regex-based by design (deterministic, explainable); entropy-based detection and additional formats can be added if an incident shows the need.
- Coverage percentage was measured on Windows; the Linux CI run will confirm identical results.
- mypy exempts test *signatures* (not bodies) per pytest convention — documented in `pyproject.toml` and `CONTRIBUTING.md`.

## Required human actions

- When convenient: `gh auth login`, then `git push -u origin main` (also triggers the first CI run). After it completes, append the run result to this report as an addendum.
- No other action required for Phase 3.

## Next phase prerequisites (Phase 4 — Storage & Data Migrations)

- Clean tree at this commit; all gates green via the commands in `CONTRIBUTING.md`.
- Phase 4 adds: SQLite access layer, versioned migrations, entity schemas, transaction/concurrency tests, backup/restore basics (per `docs/ROADMAP.md` gate).

## Rollback procedure

`git revert` the Phase 3 commit(s). All changes are additive tooling/tests/docs; removing them restores the Phase 2 baseline and changes nothing at runtime. `.venv` may be recreated with `pip install -e ".[dev]"`. No external state was touched; the remote remains empty until the owner pushes.
