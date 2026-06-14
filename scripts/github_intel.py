#!/usr/bin/env python3
"""
Merge GitHub PR and issue metadata into docs/index.json (stdlib + gh CLI).

Run after scan.py when gh is authenticated. Regenerates dashboard.html with enriched data.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from pipeline_lib import (  # noqa: E402
    build_pipeline,
    enrich_runs_for_graph,
    enrich_runs_with_jobs,
    fetch_open_pull_requests,
    fetch_workflow_runs,
)
from provenance_graph import merge_provenance_into_index  # noqa: E402
from reflect_cycle import reflect_outcomes  # noqa: E402
FIXTURE_ROOT = HERE / "test-repos"
PR_LIMIT = 30
RADAR_LABEL_PREFIX = "radar:"

CLOSES_ISSUE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.I)
TITLE_ISSUE = re.compile(r"#(\d+)")
HEAD_ISSUE = re.compile(r"^issue-(\d+)$", re.I)


def resolve_target():
    target = os.environ.get("TARGET_REPO")
    if not target:
        env = HERE / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line.startswith("TARGET_REPO=") and not line.startswith("#"):
                    target = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not target:
        target = str(HERE)
    return Path(target).expanduser().resolve()


def resolve_docs(repo):
    repo = repo.resolve()
    if repo == HERE.resolve():
        return HERE / "docs"
    try:
        repo.relative_to(FIXTURE_ROOT)
        return repo / "docs"
    except ValueError:
        return HERE / "docs"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def gh_available():
    try:
        proc = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def remote_repo_slug(repo):
    proc = git(repo, "remote", "get-url", "origin")
    if proc.returncode != 0:
        return None
    url = proc.stdout.strip()
    if not url:
        return None
    if url.startswith("git@"):
        # git@github.com:owner/repo.git
        path = url.split(":", 1)[-1]
    else:
        path = urlparse(url).path.lstrip("/")
    path = path.removesuffix(".git")
    if "/" not in path:
        return None
    return path


def run_gh(repo_slug, *args):
    cmd = ["gh", *args]
    if repo_slug:
        cmd.extend(["--repo", repo_slug])
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return proc


def parse_issue_numbers(title, body, head_ref):
    numbers = set()
    for pattern in (CLOSES_ISSUE,):
        for match in pattern.finditer(body or ""):
            numbers.add(int(match.group(1)))
    for match in TITLE_ISSUE.finditer(title or ""):
        numbers.add(int(match.group(1)))
    if head_ref:
        m = HEAD_ISSUE.match(head_ref.strip())
        if m:
            numbers.add(int(m.group(1)))
    return sorted(numbers)


def commit_files(repo, sha):
    proc = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def normalize_commits(repo, raw_commits):
    commits = []
    for item in raw_commits or []:
        node = item.get("commit") or item
        sha = item.get("oid") or item.get("sha") or ""
        full_sha = sha
        short_sha = full_sha[:7] if full_sha else ""
        message = (node.get("message") or item.get("messageHeadline") or "").split("\n")[0]
        author = node.get("author") or {}
        date = author.get("date") or item.get("committedDate") or ""
        if date and "T" in date:
            date = date.split("T")[0]
        files = commit_files(repo, full_sha) if full_sha else []
        commits.append(
            {
                "sha": short_sha,
                "full_sha": full_sha,
                "message": message,
                "date": date,
                "files": files,
            }
        )
    return commits


def fetch_issue_detail(repo_slug, number):
    proc = run_gh(
        repo_slug,
        "issue", "view", str(number),
        "--json", "number,title,state,labels",
    )
    if proc.returncode != 0:
        return None
    data = json.loads(proc.stdout)
    labels = [lb["name"] for lb in data.get("labels") or []]
    return {
        "number": data["number"],
        "title": data.get("title") or "",
        "state": data.get("state") or "OPEN",
        "labels": labels,
        "linked_prs": [],
    }


def fetch_pull_requests(repo, repo_slug):
    proc = run_gh(
        repo_slug,
        "pr", "list",
        "--state", "merged",
        "--base", "main",
        "--limit", str(PR_LIMIT),
        "--json", "number,title,body,mergedAt,headRefName,additions,deletions",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh pr list failed")

    rows = json.loads(proc.stdout or "[]")
    pull_requests = []
    for row in rows:
        number = row["number"]
        detail = run_gh(
            repo_slug,
            "pr", "view", str(number),
            "--json", "commits,files",
        )
        commits_raw = []
        files = []
        if detail.returncode == 0:
            detail_data = json.loads(detail.stdout)
            commits_raw = detail_data.get("commits") or []
            files = [f.get("path") for f in detail_data.get("files") or [] if f.get("path")]

        head_ref = row.get("headRefName") or ""
        title = row.get("title") or ""
        body = row.get("body") or ""
        issue_numbers = parse_issue_numbers(title, body, head_ref)
        labels = []
        for num in issue_numbers:
            issue = fetch_issue_detail(repo_slug, num)
            if issue:
                for label in issue["labels"]:
                    if label.startswith(RADAR_LABEL_PREFIX) and label not in labels:
                        labels.append(label)

        merged_at = row.get("mergedAt") or ""
        pull_requests.append(
            {
                "number": number,
                "title": title,
                "state": "MERGED",
                "merged_at": merged_at,
                "head_ref": head_ref,
                "issue_numbers": issue_numbers,
                "labels": labels,
                "commits": normalize_commits(repo, commits_raw),
                "files": files,
                "additions": row.get("additions") or 0,
                "deletions": row.get("deletions") or 0,
            }
        )
    return pull_requests


def fetch_radar_issues(repo_slug):
    proc = run_gh(
        repo_slug,
        "issue", "list",
        "--state", "open",
        "--limit", "100",
        "--json", "number,title,state,labels",
    )
    if proc.returncode != 0:
        return []
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
    return issues


def link_issues_to_prs(pull_requests, issues):
    by_number = {issue["number"]: issue for issue in issues}
    for pr in pull_requests:
        for num in pr.get("issue_numbers") or []:
            if num in by_number and pr["number"] not in by_number[num]["linked_prs"]:
                by_number[num]["linked_prs"].append(pr["number"])
    return list(by_number.values())


def regenerate_dashboard(index, docs):
    tmpl = (HERE / "templates" / "dashboard.html.tmpl").read_text()
    html = tmpl.replace("/*__DATA__*/", json.dumps(index))
    (docs / "dashboard.html").write_text(html)


def merge_pipeline_into_issues(issues, pipeline):
    tickets = {
        t["issue_number"]: t for t in (pipeline.get("tickets") or [])
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


def merge_github_intel(index, repo, repo_slug):
    pull_requests = fetch_pull_requests(repo, repo_slug)
    open_pull_requests = fetch_open_pull_requests(repo_slug, parse_issue_numbers)
    issues = fetch_radar_issues(repo_slug)
    issues = link_issues_to_prs(pull_requests, issues)
    for pr in open_pull_requests:
        for num in pr.get("issue_numbers") or []:
            for issue in issues:
                if issue["number"] == num and pr["number"] not in issue["linked_prs"]:
                    issue["linked_prs"].append(pr["number"])
    workflow_runs = fetch_workflow_runs(repo_slug)
    workflow_runs = enrich_runs_with_jobs(repo_slug, workflow_runs)
    workflow_runs = enrich_runs_for_graph(repo_slug, workflow_runs)
    index["pull_requests"] = pull_requests
    index["open_pull_requests"] = open_pull_requests
    index["issues"] = issues
    index["workflow_runs"] = workflow_runs
    index["pipeline"] = build_pipeline(
        issues, open_pull_requests, pull_requests, workflow_runs, repo, repo_slug
    )
    index["issues"] = merge_pipeline_into_issues(issues, index["pipeline"])
    index["github"] = {
        "repo": repo_slug,
        "pr_limit": PR_LIMIT,
        "fetched": True,
    }
    merge_provenance_into_index(index, repo)
    reflect_outcomes(index)
    return index


def main():
    docs = HERE / "docs"
    index_path = docs / "index.json"
    if not index_path.is_file():
        sys.exit(f"error: missing {index_path}; run scan.py first")

    index = json.loads(index_path.read_text())
    index.setdefault("schema_version", 1)

    repo_path = (index.get("repo") or {}).get("path")
    if repo_path:
        repo = Path(repo_path).expanduser().resolve()
    else:
        repo = resolve_target()

    if not gh_available():
        print("github_intel: gh not available or not authenticated; skipping")
        index["pull_requests"] = index.get("pull_requests") or []
        index["issues"] = index.get("issues") or []
        index["github"] = {"fetched": False, "reason": "gh unavailable"}
        index_path.write_text(json.dumps(index, indent=2))
        regenerate_dashboard(index, docs)
        return

    repo_slug = remote_repo_slug(repo)
    if not repo_slug:
        print("github_intel: could not resolve origin remote; skipping")
        index["pull_requests"] = []
        index["issues"] = []
        index["github"] = {"fetched": False, "reason": "no origin remote"}
        index_path.write_text(json.dumps(index, indent=2))
        regenerate_dashboard(index, docs)
        return

    try:
        merge_github_intel(index, repo, repo_slug)
    except RuntimeError as exc:
        print(f"github_intel: {exc}")
        index["pull_requests"] = []
        index["issues"] = []
        index["github"] = {"fetched": False, "reason": str(exc)}
    else:
        print(
            f"github_intel: {len(index['pull_requests'])} merged PR(s), "
            f"{len(index['issues'])} open radar issue(s) from {repo_slug}"
        )

    index_path.write_text(json.dumps(index, indent=2))
    try:
        sys.path.insert(0, str(HERE))
        from scan import write_sqlite  # noqa: E402

        write_sqlite(index, docs / "index.db")
    except Exception as exc:
        print(f"github_intel: sqlite refresh skipped ({exc})")
    regenerate_dashboard(index, docs)
    stats = (index.get("graph") or {}).get("stats") or {}
    if stats:
        print(
            f"github_intel: graph {stats.get('node_count', 0)} nodes, "
            f"{stats.get('edge_count', 0)} edges"
        )
    print(f"github_intel: updated {index_path} and {docs / 'dashboard.html'}")


if __name__ == "__main__":
    main()
