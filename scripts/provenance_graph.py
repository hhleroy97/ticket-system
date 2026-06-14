#!/usr/bin/env python3
"""Build git-provenance graph nodes/edges for docs/index.json (stdlib only)."""

import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone

COMMIT_LIMIT = 50
CO_CHANGE_MIN_FREQ = 2
CO_CHANGE_MIN_FILES = 2
CO_CHANGE_MAX_FILES = 50
HEAD_ISSUE = re.compile(r"^issue-(\d+)$", re.I)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def node_id(kind, key):
    return f"{kind}:{key}"


def git_commits_with_files(repo, limit=COMMIT_LIMIT):
    proc = git(repo, "log", f"-{limit}", "--format=%H%x09%s%x09%ai")
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    commits = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        sha, message, date = line.split("\t", 2)
        files_proc = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
        files = []
        if files_proc.returncode == 0:
            files = [f.strip() for f in files_proc.stdout.splitlines() if f.strip()]
        commits.append(
            {
                "sha": sha,
                "message": message.split("\n")[0][:200],
                "date": date.split()[0] if date else "",
                "files": files,
            }
        )
    return commits


def build_provenance_graph(index, repo):
    """Return graph dict with nodes, edges, stats (deterministic)."""
    file_paths = {f["path"] for f in (index.get("files") or [])}
    nodes = []
    edges = []
    seen = set()

    def add_node(node):
        if node["id"] in seen:
            return
        seen.add(node["id"])
        nodes.append(node)

    def add_edge(source, target, etype, **extra):
        edges.append({"source": source, "target": target, "type": etype, **extra})

    for f in index.get("files") or []:
        add_node(
            {
                "id": node_id("file", f["path"]),
                "kind": "file",
                "path": f["path"],
                "lang": f.get("lang"),
                "loc": f.get("loc", 0),
            }
        )

    for edge in index.get("edges") or []:
        if edge["source"] in file_paths and edge["target"] in file_paths:
            add_edge(
                node_id("file", edge["source"]),
                node_id("file", edge["target"]),
                "imports",
            )

    co_change_counts = defaultdict(int)
    commit_nodes = 0
    for commit in git_commits_with_files(repo):
        short = commit["sha"][:7]
        cid = node_id("commit", short)
        add_node(
            {
                "id": cid,
                "kind": "commit",
                "sha": short,
                "full_sha": commit["sha"],
                "message": commit["message"],
                "date": commit["date"],
            }
        )
        commit_nodes += 1
        paths = [p for p in commit["files"] if p in file_paths]
        if CO_CHANGE_MIN_FILES <= len(paths) <= CO_CHANGE_MAX_FILES:
            for i, p1 in enumerate(paths):
                for p2 in paths[i + 1 :]:
                    key = tuple(sorted((p1, p2)))
                    co_change_counts[key] += 1
        for path in paths:
            add_edge(cid, node_id("file", path), "modifies")

    co_edges = 0
    for (p1, p2), freq in co_change_counts.items():
        if freq < CO_CHANGE_MIN_FREQ:
            continue
        add_edge(
            node_id("file", p1),
            node_id("file", p2),
            "co_changed",
            weight=freq,
        )
        co_edges += 1

    def ensure_commit_node(commit):
        short = (commit.get("sha") or (commit.get("full_sha") or "")[:7])[:7]
        if not short:
            return None
        cid = node_id("commit", short)
        add_node(
            {
                "id": cid,
                "kind": "commit",
                "sha": short,
                "full_sha": commit.get("full_sha") or short,
                "message": (commit.get("message") or "")[:200],
                "date": commit.get("date") or "",
            }
        )
        return cid

    pr_count = 0
    for pr in (index.get("pull_requests") or []) + (index.get("open_pull_requests") or []):
        pid = node_id("pr", str(pr["number"]))
        add_node(
            {
                "id": pid,
                "kind": "pull_request",
                "number": pr["number"],
                "title": pr.get("title") or "",
                "state": pr.get("state") or "",
            }
        )
        pr_count += 1
        for commit in pr.get("commits") or []:
            cid = ensure_commit_node(commit)
            if cid:
                add_edge(pid, cid, "contains")
                for path in commit.get("files") or []:
                    if path in file_paths:
                        add_edge(cid, node_id("file", path), "modifies")
        for inum in pr.get("issue_numbers") or []:
            add_edge(pid, node_id("issue", str(inum)), "closes")

    issue_count = 0
    for issue in index.get("issues") or []:
        iid = node_id("issue", str(issue["number"]))
        add_node(
            {
                "id": iid,
                "kind": "issue",
                "number": issue["number"],
                "title": issue.get("title") or "",
                "stage": issue.get("stage"),
            }
        )
        issue_count += 1

    run_count = 0
    for run in index.get("workflow_runs") or []:
        run_id = run.get("id")
        if not run_id:
            continue
        rid = node_id("run", str(run_id))
        add_node(
            {
                "id": rid,
                "kind": "workflow_run",
                "run_id": run_id,
                "name": run.get("name") or "",
                "status": run.get("status") or "",
                "conclusion": run.get("conclusion") or "",
                "branch": run.get("branch") or "",
            }
        )
        run_count += 1
        branch = run.get("branch") or ""
        match = HEAD_ISSUE.match(branch)
        if match:
            add_edge(rid, node_id("issue", match.group(1)), "runs_for")
        for pr in (index.get("open_pull_requests") or []):
            if pr.get("head_ref") == branch:
                add_edge(rid, node_id("pr", str(pr["number"])), "tests")

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "commit_nodes": commit_nodes,
            "co_change_edges": co_edges,
            "pull_request_nodes": pr_count,
            "issue_nodes": issue_count,
            "workflow_run_nodes": run_count,
        },
        "built_at": utc_now(),
    }


def merge_provenance_into_index(index, repo):
    index["graph"] = build_provenance_graph(index, repo)
    index["schema_version"] = max(index.get("schema_version", 2), 3)
    return index
