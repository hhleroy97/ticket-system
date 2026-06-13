#!/usr/bin/env python3
"""Post throttled GitHub issue comments during executor agent runs."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
STATE_DIR = HERE / "docs" / "agent-runs"


def repo_slug():
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        cwd=HERE,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def load_run(issue_num):
    path = STATE_DIR / f"issue-{issue_num}" / "run.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def load_state(issue_num):
    path = STATE_DIR / f"issue-{issue_num}" / "comment_state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_state(issue_num, state):
    path = STATE_DIR / f"issue-{issue_num}"
    path.mkdir(parents=True, exist_ok=True)
    (path / "comment_state.json").write_text(json.dumps(state, indent=2))


def should_post(state, commit_count, file_count):
    last = state.get("last_commit_count"), state.get("last_file_count")
    current = commit_count, file_count
    return current != last


def post_comment(repo, issue_num, body):
    cmd = ["gh", "issue", "comment", str(issue_num), "--body", body]
    if repo:
        cmd.extend(["--repo", repo])
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "gh issue comment failed").strip()
    return None


def progress_body(issue_num, run, snapshot=False):
    commits = run.get("commit_count", 0)
    files = run.get("file_count", 0)
    kind = "snapshot" if snapshot else "update"
    lines = [
        f"**Executor {kind}** — issue #{issue_num}",
        f"- Commits on branch: **{commits}**",
        f"- Files touched: **{files}**",
    ]
    if run.get("commits"):
        lines.append("- Recent commits:")
        for c in run["commits"][-3:]:
            lines.append(f"  - `{c.get('sha', '?')}` {c.get('message', '')[:80]}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Post agent progress to GitHub issue")
    parser.add_argument("issue_num", type=int)
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--force", action="store_true", help="Post even if counts unchanged")
    args = parser.parse_args()

    run = load_run(args.issue_num)
    if not run:
        print("post_agent_progress: no run.json yet", file=sys.stderr)
        return

    state = load_state(args.issue_num)
    commits = run.get("commit_count", 0)
    files = run.get("file_count", 0)
    if not args.force and not should_post(state, commits, files):
        print("post_agent_progress: skipped (no change)")
        return

    repo = repo_slug()
    err = post_comment(repo, args.issue_num, progress_body(args.issue_num, run, args.snapshot))
    if err:
        print(f"post_agent_progress: {err}", file=sys.stderr)
        sys.exit(1)

    save_state(args.issue_num, {"last_commit_count": commits, "last_file_count": files})
    print(f"post_agent_progress: commented on #{args.issue_num}")


if __name__ == "__main__":
    main()
