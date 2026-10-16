#!/usr/bin/env python
"""Secret scanner: report credential-shaped strings in the working tree.

Scans the given paths (default: the current directory) with the deterministic,
offline rules in project_intelligence.security.secret_scan. Output lists
file:line and the matched rule name only; matched values are never printed.

Run from the repository root:

    .venv\\Scripts\\python scripts/scan_secrets.py          (Windows)
    .venv/bin/python scripts/scan_secrets.py              (Linux)

Exit codes:
    0  clean: no credential-shaped strings found
    1  findings: review, remove the material, rotate if it was ever real
    2  usage error: a given path does not exist
"""

from __future__ import annotations

import sys
from pathlib import Path

from project_intelligence.security.secret_scan import Finding, scan_tree


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets = [Path(arg) for arg in args] if args else [Path(".")]

    missing = [target for target in targets if not target.exists()]
    if missing:
        for target in missing:
            print(f"error: path does not exist: {target}")
        return 2

    findings: list[Finding] = []
    for target in targets:
        findings.extend(scan_tree(target))

    findings.sort(key=lambda f: (str(f.path), f.line_number, f.rule))
    for finding in findings:
        print(f"{finding.path}:{finding.line_number}: {finding.rule}")

    if findings:
        print()
        print(f"Result: {len(findings)} potential secret(s) found. Do not commit.")
        print("If any value was ever real, rotate it before anything else.")
        return 1

    print("Result: secret scan clean. No credential-shaped strings found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
