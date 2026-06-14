#!/usr/bin/env python3
"""Reflect on pipeline/CI outcomes and append operator feedback (stdlib only)."""

from __future__ import annotations

import json
from pathlib import Path

from operator_feedback import append_feedback, load_feedback

HERE = Path(__file__).resolve().parent.parent
AGENT_RUNS = HERE / "docs" / "agent-runs"


def already_logged(entries: list[dict], action: str, issue_number: int | None) -> bool:
    for entry in reversed(entries[-100:]):
        if entry.get("action") == action and entry.get("issue_number") == issue_number:
            return True
    return False


def plan_paths_for_issue(issue_number: int) -> set[str]:
    plan_path = AGENT_RUNS / f"issue-{issue_number}" / "plan.json"
    if not plan_path.is_file():
        return set()
    try:
        data = json.loads(plan_path.read_text())
    except (json.JSONDecodeError, OSError):
        return set()
    paths = set()
    plan = data.get("plan") or {}
    for path in plan.get("files_likely_touched") or []:
        if path:
            paths.add(path)
    for item in data.get("reach") or []:
        path = item.get("file")
        if path:
            paths.add(path)
    return paths


def runs_for_issue_branch(index: dict, issue_number: int) -> list[dict]:
    branch = f"issue-{issue_number}"
    out = []
    for run in index.get("workflow_runs") or []:
        if run.get("branch") == branch:
            out.append(run)
    return out


def reflect_outcomes(index: dict, feedback_path: Path | str | None = None) -> list[dict]:
    """Append deduped outcome feedback from workflow and agent run state."""
    entries = load_feedback(feedback_path)
    logged = []
    tickets = (index.get("pipeline") or {}).get("tickets") or []

    for ticket in tickets:
        num = ticket.get("issue_number")
        if not num:
            continue
        title = ticket.get("title") or f"issue #{num}"
        runs = runs_for_issue_branch(index, num)

        for run in runs:
            name = (run.get("name") or "").lower()
            conclusion = run.get("conclusion") or ""
            if conclusion != "failure":
                continue
            if "test" in name or name == "executor":
                action = "ci_failed"
                if not already_logged(entries + logged, action, num):
                    logged.append(
                        append_feedback(
                            action,
                            title,
                            reason=f"{run.get('name')} failed on {run.get('branch')}",
                            issue_number=num,
                            source="reflect_cycle",
                            path=feedback_path,
                        )
                    )

        for run in runs:
            name = (run.get("name") or "").lower()
            if run.get("conclusion") == "success" and "test" in name:
                action = "ci_passed"
                if not already_logged(entries + logged, action, num):
                    logged.append(
                        append_feedback(
                            action,
                            title,
                            reason=f"{run.get('name')} passed",
                            issue_number=num,
                            source="reflect_cycle",
                            path=feedback_path,
                        )
                    )

        agent = ticket.get("agent_run") or {}
        actual = set(agent.get("files") or [])
        planned = plan_paths_for_issue(num)
        if actual and planned:
            extra = sorted(path for path in actual if path not in planned)
            if extra and not already_logged(entries + logged, "blast_radius_miss", num):
                logged.append(
                    append_feedback(
                        "blast_radius_miss",
                        title,
                        reason=f"outside plan: {', '.join(extra[:5])}",
                        issue_number=num,
                        source="reflect_cycle",
                        path=feedback_path,
                    )
                )

    return logged


def main():
    index_path = HERE / "docs" / "index.json"
    if not index_path.is_file():
        raise SystemExit(f"missing {index_path}")
    index = json.loads(index_path.read_text())
    logged = reflect_outcomes(index)
    if logged:
        print(f"reflect_cycle: logged {len(logged)} outcome(s)")
    else:
        print("reflect_cycle: no new outcomes")


if __name__ == "__main__":
    main()
