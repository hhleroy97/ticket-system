#!/usr/bin/env python3
"""Capture post-agent git introspection for executor branches."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from pipeline_lib import branch_commits, branch_files, utc_now  # noqa: E402


def git(*args):
    return subprocess.run(
        ["git", "-C", str(HERE), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def diff_stat(base, head="HEAD"):
    proc = git("diff", "--stat", f"{base}...{head}")
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def capture(issue_num, base="main", snapshot=False):
    branch = f"issue-{issue_num}"
    run_dir = HERE / "docs" / "agent-runs" / f"issue-{issue_num}"
    run_dir.mkdir(parents=True, exist_ok=True)
    run_path = run_dir / "run.json"
    jsonl_path = run_dir / "run.jsonl"

    commits = branch_commits(HERE, base, "HEAD")
    files = branch_files(HERE, base, "HEAD")
    payload = {
        "issue_number": issue_num,
        "branch": branch,
        "base": base,
        "commits": commits,
        "files": files,
        "commit_count": len(commits),
        "file_count": len(files),
        "diff_stat": diff_stat(base),
        "captured_at": utc_now(),
        "partial": snapshot,
    }

    if snapshot and run_path.is_file():
        try:
            prev = json.loads(run_path.read_text())
            snaps = list(prev.get("snapshots") or [])
            snaps.append(
                {
                    "captured_at": payload["captured_at"],
                    "commit_count": payload["commit_count"],
                    "file_count": payload["file_count"],
                }
            )
            payload["snapshots"] = snaps[-20:]
        except (json.JSONDecodeError, OSError):
            pass

    run_path.write_text(json.dumps(payload, indent=2))
    if not snapshot:
        with jsonl_path.open("a") as fh:
            fh.write(json.dumps(payload) + "\n")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Capture agent run git introspection")
    parser.add_argument("issue_num", type=int)
    parser.add_argument("base", nargs="?", default="main")
    parser.add_argument("--snapshot", action="store_true", help="Progress snapshot only")
    args = parser.parse_args()
    payload = capture(args.issue_num, args.base, snapshot=args.snapshot)
    kind = "snapshot" if args.snapshot else "final"
    print(
        f"finalize_agent_run: {kind} issue-{args.issue_num} — "
        f"{payload['commit_count']} commit(s), {payload['file_count']} file(s)"
    )


if __name__ == "__main__":
    main()
