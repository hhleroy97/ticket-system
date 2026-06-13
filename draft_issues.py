#!/usr/bin/env python3
"""Draft GitHub issues from RADAR findings markdown (deterministic JSON to stdout)."""

import json
import re
import sys
from pathlib import Path

FINDING = re.compile(
    r"^##\s+(?P<title>.+?)\s*$.*?"
    r"(?:\*\*Files?\*\*:\s*(?P<files>[^\n]+))?"
    r"(?:\*\*Rationale\*\*:\s*(?P<rationale>[^\n]+))?",
    re.MULTILINE | re.DOTALL,
)


def parse_findings(text):
    issues = []
    for m in FINDING.finditer(text):
        title = m.group("title").strip()
        files = (m.group("files") or "").strip()
        rationale = (m.group("rationale") or "See RADAR findings.").strip()
        body = f"{rationale}\n\n**Files:** {files or 'n/a'}"
        issues.append({"title": title, "body": body, "rationale": rationale, "files": files})
    return issues


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: draft_issues.py docs/radar/YYYY-MM-DD.md")
    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    issues = parse_findings(path.read_text())
    json.dump(issues, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
