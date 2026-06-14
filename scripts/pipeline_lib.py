#!/usr/bin/env python3
"""Pipeline stage inference and graph data for RADAR tickets (stdlib + gh)."""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
HEAD_ISSUE = re.compile(r"^issue-(\d+)$", re.I)
AGENT_RUN_DIR = "docs/agent-runs"

PIPELINE_STAGES = [
    {"id": "proposed", "label": "Proposed", "order": 0},
    {"id": "approved", "label": "Approved", "order": 1},
    {"id": "implementing", "label": "Agent working", "order": 2},
    {"id": "verified", "label": "Verified", "order": 3},
    {"id": "pr_open", "label": "PR open", "order": 4},
    {"id": "ci", "label": "CI running", "order": 5},
    {"id": "merged", "label": "Merged", "order": 6},
]

PIPELINE_EDGES = [
    {"from": "proposed", "to": "approved"},
    {"from": "approved", "to": "implementing"},
    {"from": "implementing", "to": "verified"},
    {"from": "verified", "to": "pr_open"},
    {"from": "pr_open", "to": "ci"},
    {"from": "ci", "to": "merged"},
]

STAGE_ORDER = {s["id"]: s["order"] for s in PIPELINE_STAGES}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def run_gh(repo_slug, *args):
    cmd = ["gh", *args]
    if repo_slug:
        cmd.extend(["--repo", repo_slug])
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def issue_from_branch(branch):
    if not branch:
        return None
    match = HEAD_ISSUE.match(branch.strip())
    return int(match.group(1)) if match else None


def labels_include(labels, name):
    return name in (labels or [])


def infer_stage(issue, open_prs_by_issue, runs_by_branch, ci_branches):
    labels = issue.get("labels") or []
    number = issue["number"]
    approved = labels_include(labels, "radar:approved")
    proposed = labels_include(labels, "radar:proposed")

    open_pr = open_prs_by_issue.get(number)
    branch = f"issue-{number}"

    if open_pr:
        head = open_pr.get("head_ref") or branch
        if head in ci_branches:
            return "ci", "CI running"
        return "pr_open", "PR open"

    run = runs_by_branch.get(branch)
    if run and run.get("status") in ("in_progress", "queued", "waiting", "requested"):
        return "implementing", "Agent working"

    if run and run.get("status") == "completed":
        if run.get("conclusion") == "success":
            return "verified", "Verified"
        if run.get("conclusion") == "failure":
            return "approved", "Approved (executor failed)"

    if approved:
        return "approved", "Approved"
    if proposed:
        return "proposed", "Proposed"
    return "proposed", "Proposed"


def commit_files(repo, sha):
    proc = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def normalize_commits(repo, shas_and_messages):
    commits = []
    for short_or_full, message in shas_and_messages:
        full_sha = short_or_full
        if len(full_sha) < 40:
            proc = git(repo, "rev-parse", full_sha)
            if proc.returncode == 0:
                full_sha = proc.stdout.strip()
        commits.append(
            {
                "sha": full_sha[:7],
                "full_sha": full_sha,
                "message": message.split("\n")[0],
                "files": commit_files(repo, full_sha) if full_sha else [],
            }
        )
    return commits


def read_agent_run_file(repo, issue_number):
    path = repo / AGENT_RUN_DIR / f"issue-{issue_number}" / "run.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def branch_commits(repo, base, branch_ref):
    proc = git(repo, "log", f"{base}..{branch_ref}", "--format=%H%x09%s")
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    pairs = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        sha, msg = line.split("\t", 1)
        pairs.append((sha, msg))
    return normalize_commits(repo, pairs)


def branch_files(repo, base, branch_ref):
    proc = git(repo, "diff", "--name-only", f"{base}...{branch_ref}")
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def fetch_remote_branch(repo, branch):
    git(repo, "fetch", "origin", branch, "--quiet")


def agent_run_for_issue(repo, issue_number, base="main"):
    local = read_agent_run_file(repo, issue_number)
    branch = f"issue-{issue_number}"
    fetch_remote_branch(repo, branch)
    for ref in (branch, f"origin/{branch}"):
        commits = branch_commits(repo, base, ref)
        files = branch_files(repo, base, ref)
        if commits or files:
            payload = {
                "issue_number": issue_number,
                "branch": branch,
                "commits": commits,
                "files": files,
                "commit_count": len(commits),
                "file_count": len(files),
                "source": ref,
            }
            if local:
                payload["captured_at"] = local.get("captured_at")
                payload["partial"] = local.get("partial", False)
                if local.get("snapshots"):
                    payload["snapshots"] = local["snapshots"]
            return payload
    if local:
        return local
    return None


def fetch_open_pull_requests(repo_slug, parse_issue_numbers):
    proc = run_gh(
        repo_slug,
        "pr",
        "list",
        "--state",
        "open",
        "--base",
        "main",
        "--limit",
        "50",
        "--json",
        "number,title,body,headRefName,state,additions,deletions,url",
    )
    if proc.returncode != 0:
        return []
    rows = json.loads(proc.stdout or "[]")
    open_prs = []
    for row in rows:
        head_ref = row.get("headRefName") or ""
        title = row.get("title") or ""
        body = row.get("body") or ""
        issue_numbers = parse_issue_numbers(title, body, head_ref)
        open_prs.append(
            {
                "number": row["number"],
                "title": title,
                "state": row.get("state") or "OPEN",
                "head_ref": head_ref,
                "issue_numbers": issue_numbers,
                "additions": row.get("additions") or 0,
                "deletions": row.get("deletions") or 0,
                "url": row.get("url") or "",
            }
        )
    return open_prs


def fetch_workflow_runs(repo_slug, limit=30):
    proc = run_gh(
        repo_slug,
        "run",
        "list",
        "--limit",
        str(limit),
        "--json",
        "databaseId,name,status,conclusion,headBranch,event,createdAt,updatedAt,url",
    )
    if proc.returncode != 0:
        return []
    runs = []
    for row in json.loads(proc.stdout or "[]"):
        runs.append(
            {
                "id": row.get("databaseId"),
                "name": row.get("name") or "",
                "status": row.get("status") or "",
                "conclusion": row.get("conclusion") or "",
                "branch": row.get("headBranch") or "",
                "event": row.get("event") or "",
                "created_at": row.get("createdAt") or "",
                "updated_at": row.get("updatedAt") or "",
                "url": row.get("url") or "",
            }
        )
    return runs


def fetch_run_jobs(repo_slug, run_id):
    proc = run_gh(
        repo_slug,
        "run",
        "view",
        str(run_id),
        "--json",
        "jobs",
    )
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout or "gh run view failed").strip()
    data = json.loads(proc.stdout or "{}")
    jobs = []
    for job in data.get("jobs") or []:
        steps = []
        for step in job.get("steps") or []:
            steps.append(
                {
                    "name": step.get("name") or "",
                    "status": step.get("status") or "",
                    "conclusion": step.get("conclusion") or "",
                    "number": step.get("number"),
                }
            )
        jobs.append(
            {
                "name": job.get("name") or "",
                "status": job.get("status") or "",
                "conclusion": job.get("conclusion") or "",
                "steps": steps,
            }
        )
    return jobs, None


def ci_active_branches(runs):
    branches = set()
    for run in runs:
        if run.get("status") not in ("in_progress", "queued", "waiting", "requested"):
            continue
        name = (run.get("name") or "").lower()
        branch = run.get("branch") or ""
        if not branch:
            continue
        if name == "test" or "test" in name or run.get("event") == "pull_request":
            branches.add(branch)
    return branches


def index_runs_by_branch(runs):
    by_branch = {}
    for run in runs:
        branch = run.get("branch") or ""
        if not branch:
            continue
        if branch.startswith("issue-"):
            prev = by_branch.get(branch)
            if not prev or (run.get("updated_at") or "") >= (prev.get("updated_at") or ""):
                by_branch[branch] = run
    return by_branch


def index_open_prs_by_issue(open_prs):
    by_issue = {}
    for pr in open_prs:
        for num in pr.get("issue_numbers") or []:
            by_issue[num] = pr
    return by_issue


def executor_run_for_issue(runs_by_branch, issue_number):
    branch = f"issue-{issue_number}"
    run = runs_by_branch.get(branch)
    if not run:
        return None
    if (run.get("name") or "").lower() != "executor" and "executor" not in (
        run.get("name") or ""
    ).lower():
        return None
    active_step = None
    for job in run.get("jobs") or []:
        if job.get("status") in ("in_progress", "queued"):
            for step in job.get("steps") or []:
                if step.get("status") == "in_progress":
                    active_step = step.get("name")
                    break
            if not active_step:
                active_step = job.get("name")
    return {
        "id": run.get("id"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "url": run.get("url"),
        "active_step": active_step,
    }


def build_pipeline(issues, open_prs, merged_prs, workflow_runs, repo, repo_slug=None):
    open_by_issue = index_open_prs_by_issue(open_prs)
    runs_by_branch = index_runs_by_branch(workflow_runs)
    ci_branches = ci_active_branches(workflow_runs)

    tickets = []
    for issue in issues:
        stage_id, stage_label = infer_stage(issue, open_by_issue, runs_by_branch, ci_branches)
        agent_run = None
        if stage_id in ("implementing", "verified", "pr_open", "ci"):
            agent_run = agent_run_for_issue(repo, issue["number"])
        executor_run = executor_run_for_issue(runs_by_branch, issue["number"])
        open_pr = open_by_issue.get(issue["number"])
        ticket = {
            "issue_number": issue["number"],
            "title": issue.get("title") or "",
            "labels": issue.get("labels") or [],
            "stage": stage_id,
            "stage_label": stage_label,
            "stage_order": STAGE_ORDER.get(stage_id, 0),
            "linked_prs": issue.get("linked_prs") or [],
            "open_pr": open_pr,
            "executor_run": executor_run,
            "agent_run": agent_run,
        }
        tickets.append(ticket)

    tickets.sort(key=lambda t: (t["stage_order"], t["issue_number"]))

    return {
        "stages": PIPELINE_STAGES,
        "edges": PIPELINE_EDGES,
        "tickets": tickets,
        "open_pull_requests": open_prs,
        "updated_at": utc_now(),
    }


def enrich_runs_for_graph(repo_slug, runs, max_fetches=8):
    """Attach job steps to issue-branch runs for KG-15 provenance graph."""
    if not repo_slug:
        return runs
    enriched = []
    fetches = 0
    for run in runs:
        row = dict(run)
        branch = row.get("branch") or ""
        if branch.startswith("issue-") and not row.get("jobs") and fetches < max_fetches:
            jobs, _err = fetch_run_jobs(repo_slug, row["id"])
            row["jobs"] = jobs
            fetches += 1
        enriched.append(row)
    return enriched


def enrich_runs_with_jobs(repo_slug, runs, max_runs=5):
    if not repo_slug:
        return runs
    enriched = []
    pending = 0
    for run in runs:
        row = dict(run)
        if pending < max_runs and row.get("status") in (
            "in_progress",
            "queued",
            "waiting",
            "requested",
        ):
            jobs, _err = fetch_run_jobs(repo_slug, row["id"])
            row["jobs"] = jobs
            pending += 1
        enriched.append(row)
    return enriched
