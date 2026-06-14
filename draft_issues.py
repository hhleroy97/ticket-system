#!/usr/bin/env python3
"""Draft GitHub issues from RADAR findings markdown (deterministic JSON to stdout)."""

import json
import re
import sys
from pathlib import Path

FINDING = re.compile(
    r"^##\s+(?P<title>.+?)\s*\n"
    r"\*\*Files:\*\*\s*(?P<files>[^\n]+)\n"
    r"(?:\*\*Graph evidence:\*\*\s*(?P<graph_evidence>[^\n]+)\n)?"
    r"\*\*Rationale:\*\*\s*(?P<rationale>[^\n]+)"
    r"(?:\n\*\*Acceptance:\*\*\s*(?P<acceptance>[^\n]+))?",
    re.MULTILINE,
)

ISSUE_KEYS = ("title", "body", "rationale", "files", "graph_evidence", "acceptance")


def validate_issue(issue):
    """Return missing required keys for a parse_findings issue dict (empty when valid)."""
    required = ("title", "body", "rationale", "files")
    return [key for key in required if not issue.get(key)]


def parse_findings(text):
    issues = []
    for m in FINDING.finditer(text):
        title = m.group("title").strip()
        files = (m.group("files") or "").strip()
        rationale = (m.group("rationale") or "See RADAR findings.").strip()
        graph_evidence = (m.group("graph_evidence") or "").strip()
        acceptance = (m.group("acceptance") or "").strip()
        body_parts = [rationale, "", f"**Files:** {files or 'n/a'}"]
        if graph_evidence:
            body_parts.extend(["", f"**Graph evidence:** {graph_evidence}"])
        if acceptance:
            body_parts.extend(["", f"**Acceptance:** {acceptance}"])
        body = "\n".join(body_parts)
        issues.append(
            {
                "title": title,
                "body": body,
                "rationale": rationale,
                "files": files,
                "graph_evidence": graph_evidence,
                "acceptance": acceptance,
            }
        )
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
