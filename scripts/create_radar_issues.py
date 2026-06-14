#!/usr/bin/env python3
"""Create GitHub issues from RADAR markdown with dedup, cap, and risk labels."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts"))

from draft_issues import ISSUE_KEYS, parse_findings, validate_issue
from operator_feedback import filter_and_rank_findings, load_feedback
from radar_ticket_lib import labels_for_issue, select_issues


def validation_error(issue, missing):
    return (
        f"finding {issue.get('title', '?')!r} missing {', '.join(missing)}; "
        f"expected {', '.join(ISSUE_KEYS)} — re-run radar_report.py or update draft_issues.py"
    )


def candidates_from_report(path):
    """Parse RADAR markdown and enforce the draft_issues.py issue shape."""
    issues = []
    for issue in parse_findings(path.read_text()):
        missing = validate_issue(issue)
        if missing:
            raise ValueError(validation_error(issue, missing))
        issues.append(issue)
    return issues


def list_open_titles(repo):
    proc = subprocess.run(
        ["gh", "issue", "list", "--repo", repo, "--state", "open", "--limit", "200", "--json", "title"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [item["title"] for item in json.loads(proc.stdout)]


def create_issue(repo, issue, dry_run=False):
    labels = labels_for_issue(issue)
    body = issue["body"] + "\n\n---\n"
    if "radar:approved" in labels:
        body += "_Auto-approved (low risk). Executor will run; PR may auto-merge when tests pass._"
    else:
        body += "_Label `radar:approved` to allow the executor workflow to act._"

    if dry_run:
        print(json.dumps({"title": issue["title"], "labels": labels}))
        return

    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", issue["title"],
        "--body", body,
    ]
    for label in labels:
        cmd.extend(["--label", label])
    subprocess.run(cmd, check=True)


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: create_radar_issues.py RADAR.md [--dry-run]")
    path = Path(sys.argv[1])
    dry_run = len(sys.argv) == 3 and sys.argv[2] == "--dry-run"
    if not path.is_file():
        raise SystemExit(f"missing {path}")

    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    candidates = candidates_from_report(path)
    existing = list_open_titles(repo)
    feedback = load_feedback()
    ranked = filter_and_rank_findings(candidates, feedback)
    skipped = len(candidates) - len(ranked)
    chosen = select_issues(ranked, existing)

    if not chosen:
        msg = "no new issues to create (duplicates or empty findings)"
        if skipped:
            msg += f"; {skipped} deprioritized by operator feedback"
        print(msg)
        return

    for issue in chosen:
        create_issue(repo, issue, dry_run=dry_run)
    print(f"created {len(chosen)} issue(s)")
    if skipped:
        print(f"skipped {skipped} finding(s) deprioritized by operator feedback")


if __name__ == "__main__":
    main()
