#!/usr/bin/env python3
"""Shared logic for RADAR ticket creation (dedup, cap, risk)."""

import re

MAX_ISSUES_PER_RUN = 3
LOW_RISK_PREFIXES = ("docs/", "tests/", "test-repos/")
LOW_RISK_EXACT = frozenset({"README.md", "AGENTS.md", ".github/EXECUTOR.md"})


def normalize_title(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def is_duplicate(title, existing_titles):
    needle = normalize_title(title)
    if not needle:
        return True
    for existing in existing_titles:
        hay = normalize_title(existing)
        if not hay:
            continue
        if needle == hay or needle in hay or hay in needle:
            return True
    return False


def extract_paths(files_field, body):
    paths = re.findall(r"`([^`]+)`", files_field or "")
    if not paths:
        paths = re.findall(r"`([^`]+)`", body or "")
    return paths


def is_low_risk(issue):
    """Low risk: docs/tests/markdown only; no workflow edits."""
    paths = extract_paths(issue.get("files", ""), issue.get("body", ""))
    if not paths:
        return False
    for path in paths:
        if path.startswith(".github/workflows/"):
            return False
        if path in LOW_RISK_EXACT:
            continue
        if path.endswith(".md"):
            continue
        if any(path.startswith(prefix) for prefix in LOW_RISK_PREFIXES):
            continue
        return False
    return True


def select_issues(candidates, existing_titles, limit=MAX_ISSUES_PER_RUN):
    """Return up to `limit` non-duplicate issues."""
    chosen = []
    seen = list(existing_titles)
    for issue in candidates:
        if is_duplicate(issue["title"], seen):
            continue
        chosen.append(issue)
        seen.append(issue["title"])
        if len(chosen) >= limit:
            break
    return chosen


def labels_for_issue(issue):
    if is_low_risk(issue):
        return ["radar:approved", "radar:auto-merge"]
    return ["radar:proposed"]
