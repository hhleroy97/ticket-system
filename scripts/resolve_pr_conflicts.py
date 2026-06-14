#!/usr/bin/env python3
"""
Assess and optionally fix merge conflicts on open pull requests.

Strategy (same-repo branches only):
  1. Merge origin/main into the PR branch.
  2. If conflicts are limited to regeneratable docs artifacts, take main's version and
     rerun scan (+ github_intel when gh is available), then commit and push.
  3. Otherwise abort the merge and comment on the PR listing conflicted paths.

Stdlib + gh CLI only. Safe to run from GitHub Actions or locally:
  python3 scripts/resolve_pr_conflicts.py --all
  python3 scripts/resolve_pr_conflicts.py --pr 36 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent.parent

REGENERATABLE_EXACT = {
    "docs/index.json",
    "docs/index.db",
    "docs/dashboard.html",
}
REGENERATABLE_PREFIXES = ("docs/modules/", "docs/radar/")


@dataclass
class Assessment:
    number: int
    title: str
    head_ref: str
    mergeable: str
    merge_state: str
    cross_repo: bool
    draft: bool
    action: str
    detail: str
    conflict_files: list[str]


def run(cmd, *, cwd=None, check=True, env=None):
    return subprocess.run(
        cmd,
        cwd=cwd or HERE,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        check=check,
    )


def gh_json(args):
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY is required")
    proc = run(["gh"] + args + ["--repo", repo])
    return json.loads(proc.stdout or "null")


def is_regeneratable(path: str) -> bool:
    if path in REGENERATABLE_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in REGENERATABLE_PREFIXES)


def can_auto_resolve(conflicted: Iterable[str]) -> tuple[bool, list[str]]:
    blocked = [path for path in conflicted if not is_regeneratable(path)]
    return not blocked, blocked


def list_open_prs(pr_number: int | None) -> list[dict]:
    if pr_number is not None:
        row = gh_json(
            [
                "pr",
                "view",
                str(pr_number),
                "--json",
                "number,title,headRefName,mergeable,mergeStateStatus,isCrossRepository,isDraft,state",
            ]
        )
        if row.get("state") != "OPEN":
            return []
        return [row]
    return gh_json(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "number,title,headRefName,mergeable,mergeStateStatus,isCrossRepository,isDraft",
        ]
    )


def assess_pr(row: dict) -> Assessment:
    number = row["number"]
    mergeable = row.get("mergeable") or "UNKNOWN"
    merge_state = row.get("mergeStateStatus") or "UNKNOWN"
    cross_repo = bool(row.get("isCrossRepository"))
    draft = bool(row.get("isDraft"))

    if draft:
        action, detail = "skip", "draft PR"
    elif cross_repo:
        action, detail = "skip", "head branch is on a fork — manual resolution required"
    elif mergeable == "MERGEABLE" and merge_state == "BEHIND":
        action, detail = "behind", "branch is behind main (no conflicts yet)"
    elif mergeable == "MERGEABLE":
        action, detail = "ok", "mergeable with main"
    elif mergeable == "UNKNOWN" or merge_state == "UNKNOWN":
        action, detail = "wait", "GitHub still computing merge status"
    elif mergeable != "CONFLICTING" and merge_state != "DIRTY":
        action, detail = "skip", f"mergeable={mergeable}, mergeStateStatus={merge_state}"
    else:
        action, detail = "conflict", "merge conflicts with base branch"

    return Assessment(
        number=number,
        title=row.get("title") or "",
        head_ref=row.get("headRefName") or "",
        mergeable=mergeable,
        merge_state=merge_state,
        cross_repo=cross_repo,
        draft=draft,
        action=action,
        detail=detail,
        conflict_files=[],
    )


def comment_on_pr(number: int, body: str):
    repo = os.environ["GITHUB_REPOSITORY"]
    marker = "<!-- repo-intel-conflict-bot -->"
    if marker not in body:
        body = f"{marker}\n{body}"
    run(
        ["gh", "pr", "comment", str(number), "--repo", repo, "--body", body],
        check=False,
    )


def conflicted_files() -> list[str]:
    proc = run(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def configure_git_user():
    name = os.environ.get("GIT_AUTHOR_NAME", "github-actions[bot]")
    email = os.environ.get("GIT_AUTHOR_EMAIL", "41898282+github-actions[bot]@users.noreply.github.com")
    run(["git", "config", "user.name", name], check=False)
    run(["git", "config", "user.email", email], check=False)


def regenerate_docs():
    python = os.environ.get("PYTHON", sys.executable)
    target = str(HERE)
    env = {**os.environ, "TARGET_REPO": target}
    run([python, str(HERE / "scan.py")], env=env)
    run([python, str(HERE / "scripts" / "github_intel.py")], env=env, check=False)


def resolve_conflicts_on_branch(conflicted: list[str]) -> tuple[bool, str]:
    auto_ok, blocked = can_auto_resolve(conflicted)
    if not auto_ok:
        return False, f"non-doc conflicts: {', '.join(blocked)}"

    for path in conflicted:
        run(["git", "checkout", "--theirs", "--", path], check=False)
        run(["git", "add", "--", path], check=False)

    remaining = conflicted_files()
    if remaining:
        return False, f"unresolved after checkout --theirs: {', '.join(remaining)}"

    regenerate_docs()
    run(["git", "add", "docs"])
    return True, "regenerated docs after merging main"


def try_resolve_pr(assessment: Assessment, *, dry_run: bool) -> Assessment:
    if assessment.action not in ("conflict", "behind"):
        return assessment

    if dry_run:
        verb = "merge" if assessment.action == "behind" else "merge and attempt doc regeneration"
        assessment.detail = f"dry-run: would {verb} origin/main into {assessment.head_ref}"
        return assessment

    configure_git_user()
    run(["git", "fetch", "origin", "main"], check=True)
    run(["gh", "pr", "checkout", str(assessment.number)], check=True)

    merge_proc = run(["git", "merge", "origin/main", "--no-edit"], check=False)
    if merge_proc.returncode == 0:
        run(["git", "push", "origin", f"HEAD:{assessment.head_ref}"], check=True)
        assessment.action = "fixed"
        assessment.detail = "merged origin/main cleanly (no conflicts)"
        comment_on_pr(
            assessment.number,
            f"**Conflict bot:** merged latest `main` into `{assessment.head_ref}` — "
            "branch is up to date with base (clean merge).",
        )
        return assessment

    files = conflicted_files()
    assessment.conflict_files = files
    ok, msg = resolve_conflicts_on_branch(files)
    if not ok:
        run(["git", "merge", "--abort"], check=False)
        assessment.action = "manual"
        assessment.detail = msg
        file_list = "\n".join(f"- `{path}`" for path in files) or "- (unknown)"
        comment_on_pr(
            assessment.number,
            "**Conflict bot:** could not auto-resolve merge conflicts with `main`.\n\n"
            f"Blocked paths:\n{file_list}\n\n"
            f"Reason: {msg}\n\n"
            "Please resolve manually (`git merge origin/main` locally) or rebase onto `main`.",
        )
        return assessment

    run(
        [
            "git",
            "commit",
            "-m",
            f"chore: merge main and regenerate docs (conflict bot PR #{assessment.number})",
        ],
        check=True,
    )
    run(["git", "push", "origin", f"HEAD:{assessment.head_ref}"], check=True)
    assessment.action = "fixed"
    assessment.detail = msg
    comment_on_pr(
        assessment.number,
        "**Conflict bot:** merged `main`, auto-resolved doc conflicts, regenerated "
        "`docs/index.json` / dashboard, and pushed to "
        f"`{assessment.head_ref}`.\n\n"
        f"Conflicted paths (docs only): {', '.join(f'`{p}`' for p in files)}",
    )
    return assessment


def print_assessment(item: Assessment):
    extra = ""
    if item.conflict_files:
        extra = f" conflicts={item.conflict_files}"
    print(
        f"PR #{item.number} [{item.action}] {item.head_ref}: {item.detail}{extra}"
    )


def main():
    parser = argparse.ArgumentParser(description="Assess/fix merge conflicts on open PRs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="process all open PRs")
    group.add_argument("--pr", type=int, help="process a single PR number")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="assess only; do not merge, push, or comment fixes",
    )
    args = parser.parse_args()

    if not os.environ.get("GITHUB_REPOSITORY"):
        sys.exit("error: GITHUB_REPOSITORY is required (set by Actions or export locally)")

    pr_number = args.pr if args.pr else None
    rows = list_open_prs(pr_number)
    if not rows:
        print("resolve_pr_conflicts: no open PRs matched")
        return

    exit_code = 0
    for row in rows:
        item = assess_pr(row)
        if item.action in ("conflict", "behind"):
            item = try_resolve_pr(item, dry_run=args.dry_run)
            if item.action == "manual":
                exit_code = 1
        print_assessment(item)

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
