#!/usr/bin/env python3
"""Write a lightweight implementation plan before the executor agent runs."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
INDEX = HERE / "docs" / "index.json"


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def reach_summary_for_files(paths, depth=2):
    """Return blast-radius neighbors for planned file paths from index graph."""
    if not INDEX.is_file() or not paths:
        return []
    index = json.loads(INDEX.read_text())
    graph = index.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_by_id = {n["id"]: n for n in nodes}
    adj = {}
    for edge in edges:
        if edge.get("type") not in ("imports", "co_changed", "modifies"):
            continue
        src, tgt = edge["source"], edge["target"]
        adj.setdefault(src, set()).add(tgt)
        adj.setdefault(tgt, set()).add(src)

    summaries = []
    for path in paths:
        start = f"file:{path}"
        if start not in node_by_id:
            continue
        seen = {start}
        frontier = {start}
        for _ in range(depth):
            nxt = set()
            for node in frontier:
                for neighbor in adj.get(node, ()):
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)
                    nxt.add(neighbor)
            frontier = nxt
        neighbors = []
        for nid in sorted(seen):
            if nid == start:
                continue
            node = node_by_id.get(nid, {})
            label = node.get("path") or node.get("message") or node.get("title") or nid
            neighbors.append({"id": nid, "kind": node.get("kind"), "label": label})
        summaries.append({"file": path, "depth": depth, "neighbors": neighbors[:20]})
    return summaries


def run_plan_agent(issue_num, title, base="main"):
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        return None, "CURSOR_API_KEY not set"

    plan_dir = HERE / "docs" / "agent-runs" / f"issue-{issue_num}"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"

    prompt = (
        f"You are planning work for GitHub issue #{issue_num}: {title}. "
        "Read AGENTS.md and .github/EXECUTOR.md. Output ONLY valid JSON with keys: "
        "summary (string), steps (array of strings), files_likely_touched (array of paths), "
        "commit_plan (array of conventional commit subject lines referencing (#"
        f"{issue_num})). Keep the plan minimal."
    )
    proc = subprocess.run(
        ["cursor-agent", "-p", "--model", "auto", prompt],
        capture_output=True,
        text=True,
        env={**os.environ, "CURSOR_API_KEY": api_key},
        timeout=180,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "cursor-agent plan failed").strip()
        return None, err[:2000]

    raw = (proc.stdout or "").strip()
    plan_body = {"summary": raw, "steps": [], "files_likely_touched": [], "commit_plan": []}
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            plan_body = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass

    payload = {
        "issue_number": issue_num,
        "title": title,
        "base": base,
        "created_at": utc_now(),
        "plan": plan_body,
        "reach": reach_summary_for_files(plan_body.get("files_likely_touched") or []),
    }
    plan_path.write_text(json.dumps(payload, indent=2))
    return payload, None


def main():
    parser = argparse.ArgumentParser(description="Generate executor plan JSON")
    parser.add_argument("issue_num", type=int)
    parser.add_argument("title")
    parser.add_argument("base", nargs="?", default="main")
    args = parser.parse_args()
    payload, err = run_plan_agent(args.issue_num, args.title, args.base)
    if err:
        print(f"agent_plan: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"agent_plan: wrote plan for issue-{args.issue_num}")


if __name__ == "__main__":
    main()
