#!/usr/bin/env python3
"""
Assess and optionally fix merge conflicts on open pull requests.

Strategy (same-repo branches only):
  1. Merge origin/main into the PR branch.
  2. If conflicts are limited to regeneratable docs artifacts, take main's version and
     rerun scan (+ github_intel when gh is available), then commit and push.
  3. If code conflicts remain, invoke a scoped Composer executor agent
     (scripts/run_conflict_agent.sh) to resolve only conflicted paths, run tests, and push.
  4. If the agent is unavailable or ineligible, abort and comment on the PR.

Stdlib + gh CLI (+ cursor-agent when CURSOR_API_KEY is set). Safe to run from CI:
  python3 scripts/resolve_pr_conflicts.py --all
  python3 scripts/resolve_pr_conflicts.py --pr 36 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent.parent
MAX_AGENT_FILES = 12
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")

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
    conflict_files: list[str] = field(default_factory=list)


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


def split_conflicts(conflicted: Iterable[str]) -> tuple[list[str], list[str]]:
    docs, code = [], []
    for path in conflicted:
        if is_regeneratable(path):
            docs.append(path)
        else:
            code.append(path)
    return docs, code


def can_auto_resolve(conflicted: Iterable[str]) -> tuple[bool, list[str]]:
    blocked = [path for path in conflicted if not is_regeneratable(path)]
    return not blocked, blocked


def agent_enabled(explicit: bool | None) -> bool:
    if explicit is False:
        return False
    if explicit is True:
        return bool(os.environ.get("CURSOR_API_KEY"))
    # default: use agent when key present (CI) or CONFLICT_AGENT=1 locally
    if os.environ.get("CONFLICT_AGENT", "").lower() in ("0", "false", "no"):
        return False
    return bool(os.environ.get("CURSOR_API_KEY"))


def is_agent_eligible(code_files: list[str]) -> tuple[bool, str]:
    if not code_files:
        return False, "no code conflicts"
    if len(code_files) > MAX_AGENT_FILES:
        return False, f"too many conflicted files ({len(code_files)} > {MAX_AGENT_FILES})"
    for path in code_files:
        if path.startswith(".github/workflows/"):
            return False, "workflow file conflicts require maintainer PAT"
    return True, ""


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


def files_with_markers(paths: Iterable[str]) -> list[str]:
    bad = []
    for rel in paths:
        path = HERE / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if any(marker in text for marker in CONFLICT_MARKERS):
            bad.append(rel)
    return bad


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


def resolve_doc_conflicts(doc_files: list[str]) -> tuple[bool, str]:
    if not doc_files:
        return True, ""
    for path in doc_files:
        run(["git", "checkout", "--theirs", "--", path], check=False)
        run(["git", "add", "--", path], check=False)
    remaining = [path for path in doc_files if path in conflicted_files()]
    if remaining:
        return False, f"doc conflicts unresolved: {', '.join(remaining)}"
    regenerate_docs()
    run(["git", "add", "docs"], check=False)
    return True, "regenerated docs"


def run_tests() -> tuple[bool, str]:
    python = os.environ.get("PYTHON", sys.executable)
    proc = run([python, str(HERE / "run_tests.py")], check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "run_tests failed").strip().splitlines()
        return False, tail[-1] if tail else "run_tests failed"
    return True, "tests passed"


def run_conflict_agent(pr_number: int, head_ref: str, code_files: list[str]) -> tuple[bool, str]:
    script = HERE / "scripts" / "run_conflict_agent.sh"
    if not script.is_file():
        return False, "run_conflict_agent.sh missing"
    csv = ",".join(code_files)
    proc = run(["bash", str(script), str(pr_number), head_ref, csv], check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "conflict agent failed").strip()
        return False, err.splitlines()[-1][:500]
    return True, "scoped conflict agent finished"


def complete_merge_commit(pr_number: int, scoped_files: list[str]) -> None:
    remaining = conflicted_files()
    if remaining:
        raise RuntimeError(f"still conflicted: {remaining}")
    markers = files_with_markers(scoped_files)
    if markers:
        raise RuntimeError(f"conflict markers remain in: {markers}")
    run(
        [
            "git",
            "commit",
            "--no-edit",
            "-m",
            f"chore: resolve merge conflicts with main (PR #{pr_number})",
        ],
        check=True,
    )


def resolve_merge_conflicts(
    assessment: Assessment,
    files: list[str],
    *,
    use_agent: bool,
) -> tuple[bool, str, str]:
    """Return (ok, detail, resolution_kind). kind: docs|agent|none"""
    doc_files, code_files = split_conflicts(files)

    if doc_files:
        ok, msg = resolve_doc_conflicts(doc_files)
        if not ok:
            return False, msg, "none"

    remaining = conflicted_files()
    if not remaining:
        tests_ok, test_msg = run_tests()
        if not tests_ok:
            return False, test_msg, "none"
        try:
            complete_merge_commit(assessment.number, doc_files)
        except RuntimeError as exc:
            return False, str(exc), "none"
        return True, f"doc conflicts resolved; {test_msg}", "docs"

    _, code_remaining = split_conflicts(remaining)
    if not code_remaining:
        tests_ok, test_msg = run_tests()
        if not tests_ok:
            return False, test_msg, "none"
        try:
            complete_merge_commit(assessment.number, doc_files)
        except RuntimeError as exc:
            return False, str(exc), "none"
        return True, f"doc conflicts resolved; {test_msg}", "docs"

    eligible, reason = is_agent_eligible(code_remaining)
    if not eligible:
        return False, reason or "agent ineligible", "none"

    if not agent_enabled(use_agent):
        return False, "semantic conflicts require CURSOR_API_KEY / scoped agent", "none"

    ok, msg = run_conflict_agent(assessment.number, assessment.head_ref, code_remaining)
    if not ok:
        return False, msg, "none"

    markers = files_with_markers(code_remaining)
    if markers or conflicted_files():
        return False, f"agent left conflicts in {markers or conflicted_files()}", "none"

    tests_ok, test_msg = run_tests()
    if not tests_ok:
        return False, test_msg, "none"

    try:
        complete_merge_commit(assessment.number, code_remaining)
    except RuntimeError as exc:
        return False, str(exc), "none"

    run(["git", "add", f"docs/agent-runs/pr-{assessment.number}/"], check=False)
    if not run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        run(
            [
                "git",
                "commit",
                "-m",
                f"docs: conflict agent trace for PR #{assessment.number}",
            ],
            check=False,
        )

    return True, f"agent resolved {len(code_remaining)} file(s); {test_msg}", "agent"


def abort_merge():
    run(["git", "merge", "--abort"], check=False)


def try_resolve_pr(assessment: Assessment, *, dry_run: bool, use_agent: bool | None) -> Assessment:
    if assessment.action not in ("conflict", "behind"):
        return assessment

    if dry_run:
        agent_note = ""
        if agent_enabled(use_agent):
            agent_note = "; would invoke scoped conflict agent for code conflicts"
        verb = "merge" if assessment.action == "behind" else "merge and resolve conflicts"
        assessment.detail = f"dry-run: would {verb} origin/main into {assessment.head_ref}{agent_note}"
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

    ok, msg, kind = resolve_merge_conflicts(assessment, files, use_agent=use_agent)
    if ok:
        run(["git", "push", "origin", f"HEAD:{assessment.head_ref}"], check=True)
        assessment.action = "fixed"
        assessment.detail = msg
        if kind == "docs":
            comment_on_pr(
                assessment.number,
                "**Conflict bot:** merged `main`, auto-resolved doc conflicts, regenerated "
                f"artifacts, and pushed to `{assessment.head_ref}`.\n\n"
                f"Paths: {', '.join(f'`{p}`' for p in files)}",
            )
        else:
            comment_on_pr(
                assessment.number,
                "**Conflict bot:** merged `main`, scoped **Composer agent** resolved semantic "
                f"conflicts, tests passed, and pushed to `{assessment.head_ref}`.\n\n"
                f"Agent trace: `docs/agent-runs/pr-{assessment.number}/run.json`",
            )
        return assessment

    abort_merge()
    assessment.action = "manual"
    assessment.detail = msg
    file_list = "\n".join(f"- `{path}`" for path in files) or "- (unknown)"
    agent_hint = ""
    if not agent_enabled(use_agent):
        agent_hint = "\n\n_Set `CURSOR_API_KEY` in repo secrets to enable scoped agent resolution._"
    comment_on_pr(
        assessment.number,
        "**Conflict bot:** could not auto-resolve merge conflicts with `main`.\n\n"
        f"Blocked paths:\n{file_list}\n\n"
        f"Reason: {msg}{agent_hint}\n\n"
        "Resolve manually (`git merge origin/main`) or re-run with agent enabled.",
    )
    return assessment


def print_assessment(item: Assessment):
    extra = ""
    if item.conflict_files:
        extra = f" conflicts={item.conflict_files}"
    print(f"PR #{item.number} [{item.action}] {item.head_ref}: {item.detail}{extra}")


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
    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="never invoke scoped conflict agent (doc auto-fix only)",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="require scoped conflict agent for code conflicts (needs CURSOR_API_KEY)",
    )
    args = parser.parse_args()

    if not os.environ.get("GITHUB_REPOSITORY"):
        sys.exit("error: GITHUB_REPOSITORY is required (set by Actions or export locally)")

    use_agent = False if args.no_agent else True if args.agent else None
    pr_number = args.pr if args.pr else None
    rows = list_open_prs(pr_number)
    if not rows:
        print("resolve_pr_conflicts: no open PRs matched")
        return

    exit_code = 0
    for row in rows:
        item = assess_pr(row)
        if item.action in ("conflict", "behind"):
            item = try_resolve_pr(item, dry_run=args.dry_run, use_agent=use_agent)
            if item.action == "manual":
                exit_code = 1
        print_assessment(item)

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
