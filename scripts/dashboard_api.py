#!/usr/bin/env python3
"""Dashboard local API helpers (gh CLI) — approve issues, poll workflows."""

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from pipeline_lib import enrich_runs_with_jobs, fetch_run_jobs  # noqa: E402
from graph_lib import reach_query  # noqa: E402

INDEX = HERE / "docs" / "index.json"
RADAR_LABEL_PREFIX = "radar:"
WORKFLOW_LIMIT = 20

ISSUE_PATH = re.compile(r"^/api/issues/(\d+)(?:/approve)?$")
WORKFLOW_RUN_PATH = re.compile(r"^/api/workflows/(\d+)$")


def load_index():
    if not INDEX.is_file():
        return {}
    return json.loads(INDEX.read_text())


def repo_slug():
    index = load_index()
    slug = (index.get("github") or {}).get("repo")
    if slug:
        return slug
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        cwd=HERE,
    )
    if proc.returncode == 0:
        return proc.stdout.strip() or None
    return None


def gh_available():
    try:
        proc = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def run_gh(repo_slug, *args):
    cmd = ["gh", *args]
    if repo_slug:
        cmd.extend(["--repo", repo_slug])
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def enrich_issues_from_index(issues, index):
    tickets = {
        t["issue_number"]: t
        for t in (index.get("pipeline") or {}).get("tickets") or []
    }
    for issue in issues:
        ticket = tickets.get(issue["number"])
        if not ticket:
            continue
        issue["stage"] = ticket.get("stage")
        issue["stage_label"] = ticket.get("stage_label")
        issue["agent_run"] = ticket.get("agent_run")
        issue["executor_run"] = ticket.get("executor_run")
        issue["open_pr"] = ticket.get("open_pr")
    return issues


def link_issues_to_prs_in_index(issues, index):
    by_number = {issue["number"]: issue for issue in issues}
    for key in ("pull_requests", "open_pull_requests"):
        for pr in index.get(key) or []:
            for num in pr.get("issue_numbers") or []:
                if num in by_number and pr["number"] not in by_number[num]["linked_prs"]:
                    by_number[num]["linked_prs"].append(pr["number"])
    return list(by_number.values())


def fetch_radar_issues(repo_slug):
    proc = run_gh(
        repo_slug,
        "issue", "list",
        "--state", "open",
        "--limit", "100",
        "--json", "number,title,state,labels",
    )
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "gh issue list failed").strip()
    issues = []
    for row in json.loads(proc.stdout or "[]"):
        labels = [lb["name"] for lb in row.get("labels") or []]
        if not any(lb.startswith(RADAR_LABEL_PREFIX) for lb in labels):
            continue
        issues.append(
            {
                "number": row["number"],
                "title": row.get("title") or "",
                "state": row.get("state") or "OPEN",
                "labels": labels,
                "linked_prs": [],
            }
        )
    index = load_index()
    issues = link_issues_to_prs_in_index(issues, index)
    issues = enrich_issues_from_index(issues, index)
    return issues, None


def approve_issue(repo_slug, issue_number, auto_merge=False):
    labels_add = ["radar:approved"]
    if auto_merge:
        labels_add.append("radar:auto-merge")
    cmd = ["gh", "issue", "edit", str(issue_number)]
    if repo_slug:
        cmd.extend(["--repo", repo_slug])
    cmd.extend(["--remove-label", "radar:proposed"])
    for label in labels_add:
        cmd.extend(["--add-label", label])
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "gh issue edit failed").strip()
    return {
        "number": issue_number,
        "labels_added": labels_add,
        "labels_removed": ["radar:proposed"],
    }, None


def fetch_workflow_runs(repo_slug, limit=WORKFLOW_LIMIT, with_jobs=True):
    proc = run_gh(
        repo_slug,
        "run", "list",
        "--limit", str(limit),
        "--json", "databaseId,name,status,conclusion,headBranch,event,createdAt,updatedAt,url",
    )
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "gh run list failed").strip()
    runs = []
    for row in json.loads(proc.stdout or "[]"):
        runs.append(
            {
                "id": row.get("databaseId"),
                "name": row.get("name") or "",
                "title": "",
                "status": row.get("status") or "",
                "conclusion": row.get("conclusion") or "",
                "branch": row.get("headBranch") or "",
                "event": row.get("event") or "",
                "created_at": row.get("createdAt") or "",
                "updated_at": row.get("updatedAt") or "",
                "url": row.get("url") or "",
            }
        )
    if with_jobs:
        runs = enrich_runs_with_jobs(repo_slug, runs)
    return runs, None


def fetch_workflow_run_detail(repo_slug, run_id):
    jobs, err = fetch_run_jobs(repo_slug, run_id)
    if err:
        return None, err
    return {"id": run_id, "jobs": jobs}, None


def query_reach(path, depth=2):
    index = load_index()
    return reach_query(path, depth=depth, index=index)


def parse_api_path(path, method):
    """Return (resource, issue_number) for /api/issues/123/approve etc."""
    if path == "/api/workflows" and method == "GET":
        return ("workflows", None)
    if path.startswith("/api/reach") and method == "GET":
        return ("reach", None)
    m = WORKFLOW_RUN_PATH.match(path)
    if m and method == "GET":
        return ("workflow_run", int(m.group(1)))
    if path == "/api/issues" and method == "GET":
        return ("issues", None)
    m = ISSUE_PATH.match(path)
    if m and method == "POST" and path.endswith("/approve"):
        return ("approve", int(m.group(1)))
    return (None, None)
