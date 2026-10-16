#!/usr/bin/env python
"""Non-destructive configuration check for Discord Project Intelligence.

Loads and validates the effective configuration (environment + optional .env),
prints a secret-free summary, and runs read-only prerequisite checks on
referenced files and commands. It performs no writes and no network access.

Run from the repository root:

    .venv\\Scripts\\python scripts/validate_config.py    (Windows)
    .venv/bin/python scripts/validate_config.py        (Linux)

Exit codes:
    0  configuration valid (prerequisite checks may contain info notes)
    2  configuration invalid (nothing was changed)
    3  configuration valid, but runtime prerequisite errors exist
"""

from __future__ import annotations

import sys

from project_intelligence.config import ConfigError, load_settings
from project_intelligence.diagnostics import (
    check_runtime_prerequisites,
    format_summary,
    summarize_settings,
)


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(str(exc))
        print()
        print("Result: configuration INVALID. No secrets were printed, and nothing was changed.")
        return 2

    print(format_summary(summarize_settings(settings)))
    print()

    checks = check_runtime_prerequisites(settings)
    if checks:
        print("Runtime prerequisite checks (read-only):")
        for level, message in checks:
            print(f"  [{level}] {message}")
        print()

    if any(level == "error" for level, _ in checks):
        print("Result: configuration valid, but runtime prerequisites have errors.")
        return 3

    print("Result: configuration valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
