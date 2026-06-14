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
sys.path.insert(0, str(HERE / "scripts"))

from graph_lib import co_change_neighbors, load_index as load_graph_index, load_provenance, reach_query  # noqa: E402


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def reach_summary_for_files(paths, depth=2, index_path=None):
    """Return blast-radius and co-change context for planned file paths."""
    path = Path(index_path) if index_path else INDEX
    if not path.is_file() or not paths:
        return []
    index = load_graph_index(path)
    _, edges, _ = load_provenance(index)

    summaries = []
    for file_path in paths:
        reach = reach_query(file_path, depth=depth, index=index)
        co = co_change_neighbors(file_path, edges)
        summaries.append(
            {
                "file": file_path,
                "depth": depth,
                "neighbors": (reach.get("reachable") or [])[:20],
                "co_changed": [{"path": p, "weight": w} for p, w in co[:10]],
            }
        )
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
