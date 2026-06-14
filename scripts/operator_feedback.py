#!/usr/bin/env python3
"""Operator feedback log — steers RADAR ticket selection from approve/reject signals."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from radar_ticket_lib import normalize_title

HERE = Path(__file__).resolve().parent.parent
DEFAULT_PATH = HERE / "docs" / "operator-feedback.jsonl"

REJECT_ACTIONS = frozenset({"rejected", "dismissed", "closed"})
APPROVE_ACTIONS = frozenset({"approved", "merged", "request_created"})
OUTCOME_PENALTY_ACTIONS = frozenset({"ci_failed", "blast_radius_miss"})
OUTCOME_BOOST_ACTIONS = frozenset({"ci_passed"})
SKIP_AFTER_REJECTIONS = 2


def feedback_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else DEFAULT_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_feedback(path: Path | str | None = None) -> list[dict]:
    fb = feedback_path(path)
    if not fb.is_file():
        return []
    entries = []
    for line in fb.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def append_feedback(
    action: str,
    title: str,
    *,
    reason: str = "",
    issue_number: int | None = None,
    source: str = "operator",
    path: Path | str | None = None,
) -> dict:
    entry = {
        "ts": utc_now(),
        "action": action,
        "title": title,
        "reason": reason,
        "issue_number": issue_number,
        "source": source,
    }
    fb = feedback_path(path)
    fb.parent.mkdir(parents=True, exist_ok=True)
    with fb.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def titles_similar(a: str, b: str) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    wa, wb = set(na.split()), set(nb.split())
    return len(wa & wb) >= 2


def rejection_count(title: str, entries: list[dict]) -> int:
    return sum(
        1
        for entry in entries
        if entry.get("action") in REJECT_ACTIONS and titles_similar(title, entry.get("title", ""))
    )


def approval_count(title: str, entries: list[dict]) -> int:
    return sum(
        1
        for entry in entries
        if entry.get("action") in APPROVE_ACTIONS and titles_similar(title, entry.get("title", ""))
    )


def should_skip_finding(title: str, entries: list[dict]) -> bool:
    return rejection_count(title, entries) >= SKIP_AFTER_REJECTIONS


def outcome_penalty_count(title: str, entries: list[dict]) -> int:
    return sum(
        1
        for entry in entries
        if entry.get("action") in OUTCOME_PENALTY_ACTIONS
        and titles_similar(title, entry.get("title", ""))
    )


def score_finding(title: str, entries: list[dict]) -> int:
    if should_skip_finding(title, entries):
        return -1000
    score = approval_count(title, entries) * 2
    score -= outcome_penalty_count(title, entries) * 3
    score += sum(
        1
        for entry in entries
        if entry.get("action") in OUTCOME_BOOST_ACTIONS
        and titles_similar(title, entry.get("title", ""))
    )
    return score


def feedback_summary(entries: list[dict] | None = None, limit: int = 12) -> dict:
    rows = entries if entries is not None else load_feedback()
    counts: dict[str, int] = {}
    for entry in rows:
        action = entry.get("action") or "unknown"
        counts[action] = counts.get(action, 0) + 1
    return {
        "total": len(rows),
        "counts": counts,
        "recent": list(reversed(rows[-limit:])),
    }


def filter_and_rank_findings(candidates: list[dict], entries: list[dict]) -> list[dict]:
    kept = [c for c in candidates if not should_skip_finding(c.get("title", ""), entries)]
    return sorted(
        kept,
        key=lambda c: (-score_finding(c.get("title", ""), entries), c.get("title", "")),
    )
