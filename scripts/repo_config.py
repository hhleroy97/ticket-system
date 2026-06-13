#!/usr/bin/env python3
"""Repo paths for scan vs intel artifact root (ticket-sys checkout)."""

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = HERE / "test-repos"


def load_env_file():
    values = {}
    env_path = HERE / ".env"
    if not env_path.is_file():
        return values
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def intel_root():
    """Checkout that owns docs/ and GitHub intel (always this repo)."""
    return HERE.resolve()


def resolve_target_repo():
    """
    Repo to analyze for dependency graph / churn.

    Order: TARGET_REPO env → .env → intel root.
    """
    target = os.environ.get("TARGET_REPO")
    if not target:
        target = load_env_file().get("TARGET_REPO")
    if not target:
        return intel_root()
    return Path(target).expanduser().resolve()


def resolve_hook_scan_repo():
    """Pre-commit always scans the intel checkout, not TARGET_REPO."""
    return intel_root()


def resolve_docs(scan_repo):
    scan_repo = scan_repo.resolve()
    root = intel_root()
    if scan_repo == root:
        return root / "docs"
    try:
        scan_repo.relative_to(FIXTURE_ROOT)
        return scan_repo / "docs"
    except ValueError:
        return root / "docs"
