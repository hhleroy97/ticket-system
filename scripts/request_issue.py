#!/usr/bin/env python3
"""Create a radar:proposed GitHub issue from an operator request."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from operator_feedback import append_feedback  # noqa: E402


def build_title(message: str) -> str:
    first = message.strip().splitlines()[0].strip()
    if len(first) > 72:
        first = first[:69] + "..."
    if not re.match(r"^(feat|fix|docs|request|refactor|test):", first, re.I):
        first = f"request: {first[:64]}"
    return first


def build_body(message: str, acceptance: str | None = None) -> str:
    accept = (acceptance or "").strip() or "_Define acceptance criteria before approving._"
    return (
        f"**Request:** {message.strip()}\n\n"
        f"**Acceptance:** {accept}\n\n"
        "**Files:** _n/a (operator request)_\n\n"
        "---\n"
        "_Created from dashboard or CLI. Label `radar:approved` to run the executor._"
    )


def create_request_issue(
    repo_slug: str,
    message: str,
    *,
    acceptance: str | None = None,
    dry_run: bool = False,
) -> tuple[dict | None, str | None]:
    message = (message or "").strip()
    if not message:
        return None, "message required"

    title = build_title(message)
    body = build_body(message, acceptance)
    labels = ["radar:proposed", "radar:request"]

    if dry_run:
        return {"title": title, "labels": labels, "body": body}, None

    cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        repo_slug,
        "--title",
        title,
        "--body",
        body,
    ]
    for label in labels:
        cmd.extend(["--label", label])
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "gh issue create failed").strip()

    url = (proc.stdout or "").strip()
    issue_number = None
    m = re.search(r"/issues/(\d+)", url)
    if m:
        issue_number = int(m.group(1))

    append_feedback(
        "request_created",
        title,
        reason=message[:200],
        issue_number=issue_number,
        source="request_issue",
    )
    return {"title": title, "url": url, "number": issue_number, "labels": labels}, None


def main():
    parser = argparse.ArgumentParser(description="Create GitHub issue from operator request")
    parser.add_argument("message", help="what you want built")
    parser.add_argument("--acceptance", default="", help="acceptance criteria")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit("gh repo view failed — run gh auth login")
    repo = proc.stdout.strip()
    result, err = create_request_issue(
        repo,
        args.message,
        acceptance=args.acceptance or None,
        dry_run=args.dry_run,
    )
    if err:
        raise SystemExit(err)
    print(result.get("url") or result)


if __name__ == "__main__":
    main()
