#!/usr/bin/env python3
"""Background git sync helpers for the local dashboard server."""

import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SYNC_SCRIPT = HERE / "hooks" / "sync-origin-main.sh"

_lock = threading.Lock()
_state = {
    "last_run": None,
    "ok": None,
    "message": "not started",
    "branch": None,
    "head": None,
    "origin_main": None,
    "behind": None,
    "ahead": None,
}


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(HERE), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def git_branch_status():
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    head = _git("rev-parse", "--short", "HEAD").stdout.strip()
    origin = _git("rev-parse", "--short", "origin/main").stdout.strip() if _git(
        "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"
    ).returncode == 0 else None
    behind, ahead = 0, 0
    if origin:
        proc = _git("rev-list", "--left-right", "--count", "HEAD...origin/main")
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
    return {
        "branch": branch,
        "head": head,
        "origin_main": origin,
        "behind": behind,
        "ahead": ahead,
    }


def run_sync(stay=True):
    """Fetch origin and fast-forward main when possible."""
    if not SYNC_SCRIPT.is_file():
        return False, "sync script missing"

    cmd = ["bash", str(SYNC_SCRIPT)]
    if stay:
        cmd.append("--stay")
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", cwd=HERE)
    message = (proc.stdout or proc.stderr or "").strip() or ("ok" if proc.returncode == 0 else "sync failed")
    return proc.returncode == 0, message


def sync_once(stay=True):
    """Run sync and update shared state."""
    ok, message = run_sync(stay=stay)
    status = git_branch_status()
    with _lock:
        _state.update(
            {
                "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "ok": ok,
                "message": message.splitlines()[-1] if message else "",
                **status,
            }
        )
    return dict(_state)


def get_state():
    with _lock:
        return dict(_state)


def start_background_sync(interval_sec=60, stay=True):
    """Start daemon thread that syncs on a fixed interval."""

    def loop():
        while True:
            try:
                sync_once(stay=stay)
            except Exception as exc:  # pragma: no cover - defensive
                with _lock:
                    _state["ok"] = False
                    _state["message"] = str(exc)
                    _state["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            threading.Event().wait(interval_sec)

    thread = threading.Thread(target=loop, name="repo-sync", daemon=True)
    thread.start()
    return thread
