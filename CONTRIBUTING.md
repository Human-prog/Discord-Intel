# Contributing

This is a private, phase-gated repository. Read `docs/ROADMAP.md` and the most
recent `docs/phases/PHASE_*.md` report before changing anything.

## Ground rules

- Work through the phases in order. Each phase ends with tests, a phase report
  in `docs/phases/` containing real evidence, and a rollback path.
- Never claim something was tested unless it actually ran. Label claims as
  Verified / Reported / Inferred / Unknown.
- Never commit secrets, real tokens, private data, or private host details.
- Never push to any remote without explicit owner approval
  (see `docs/OPERATIONS.md`, section 4).
- The initial release is strictly read-only: the bot never edits repositories,
  opens pull requests, runs arbitrary shell commands, installs packages, or
  changes host or network state.

## Development setup

Windows (PowerShell), from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[dev]"
```

Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

## Quality gates (must pass before every commit)

```powershell
.venv\Scripts\python -m pytest -q --cov
.venv\Scripts\ruff check .
.venv\Scripts\ruff format --check .
.venv\Scripts\python -m mypy .
.venv\Scripts\pip-audit --progress-spinner off
.venv\Scripts\python scripts\scan_secrets.py
```

Linux: replace `.venv\Scripts\` with `.venv/bin/` and use `ruff` / `pip-audit`
directly. CI (`.github/workflows/ci.yml`) runs all of these on `ubuntu-latest`
against the pinned `requirements.lock`.

## Tests

- `tests/unit/` for pure logic, `tests/security/` for security properties
  (integration tests arrive with the health engine in Phase 6).
- Branch coverage must stay at or above the `fail_under` gate in
  `pyproject.toml`; the suite currently runs at 100%.
- Fixtures that need credential-shaped strings must construct them
  programmatically, e.g. `"ghp_" + "a" * 30`. The test
  `tests/security/test_scan_secrets.py::test_repository_tree_is_clean`
  enforces that the working tree stays scanner-clean.

## Style

- Ruff decides formatting and lint (line length 100, security rules enabled).
- `src/` and `scripts/` require complete type annotations; test functions may
  omit signatures per pytest convention, but their bodies are still
  type-checked.
- Start modules with `from __future__ import annotations`; keep CLI output
  ASCII-safe.

## Security

Read `docs/SECURITY.md` before touching authentication, redaction, networking,
or anything that handles credentials - especially the response procedure for
accidental secret exposure.
