#!/usr/bin/env python3
"""Background refresh of docs/index.json for the local dashboard."""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from repo_config import resolve_target_repo  # noqa: E402

INDEX = HERE / "docs" / "index.json"

_lock = threading.Lock()
_state = {
    "last_intel": None,
    "last_scan": None,
    "intel_ok": None,
    "scan_ok": None,
    "message": "",
}


def _run(cmd, env=None, timeout=180):
    return subprocess.run(
        cmd,
        cwd=HERE,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def refresh_github_intel():
    """Fetch latest PR/issue metadata into index.json."""
    proc = _run([os.environ.get("PYTHON", "python3"), str(HERE / "scripts" / "github_intel.py")])
    ok = proc.returncode == 0
    msg = (proc.stdout or proc.stderr or "").strip().splitlines()
    return ok, msg[-1] if msg else ("ok" if ok else "github_intel failed")


def refresh_scan():
    """Rescan monitored repo (TARGET_REPO) and refresh GitHub intel."""
    target = resolve_target_repo()
    env = {**os.environ, "TARGET_REPO": str(target)}
    proc = _run([os.environ.get("PYTHON", "python3"), str(HERE / "scan.py")], env=env, timeout=240)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "scan failed").strip()
        return False, err.splitlines()[-1]
    ok, msg = refresh_github_intel()
    return ok, msg


def read_index_payload():
    """Return dashboard-relevant slice of index.json."""
    if not INDEX.is_file():
        return {}
    index = json.loads(INDEX.read_text())
    return {
        "repo": index.get("repo") or {},
        "meta": index.get("meta") or {},
        "stats": index.get("stats") or {},
        "pull_requests": index.get("pull_requests") or [],
        "open_pull_requests": index.get("open_pull_requests") or [],
        "issues": index.get("issues") or [],
        "pipeline": index.get("pipeline") or {},
        "github": index.get("github") or {},
        "generated_at": (index.get("repo") or {}).get("generated_at"),
    }


def get_refresh_state():
    with _lock:
        return dict(_state)


def _set_state(intel_ok=None, scan_ok=None, message=""):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if intel_ok is not None:
        _state["last_intel"] = now
        _state["intel_ok"] = intel_ok
    if scan_ok is not None:
        _state["last_scan"] = now
        _state["scan_ok"] = scan_ok
    if message:
        _state["message"] = message


def refresh_intel_once():
    with _lock:
        ok, msg = refresh_github_intel()
        _set_state(intel_ok=ok, message=msg)
        return ok, msg


def refresh_all_once():
    with _lock:
        ok, msg = refresh_scan()
        _set_state(intel_ok=ok, scan_ok=ok, message=msg)
        return ok, msg


def start_background_refresh(intel_interval_sec=15, scan_interval_sec=90):
    """Poll GitHub intel often; rescan repo less often."""

    def loop():
        last_scan_at = 0.0
        while True:
            try:
                refresh_intel_once()
            except Exception as exc:  # pragma: no cover
                with _lock:
                    _set_state(intel_ok=False, message=str(exc))
            now = time.time()
            if now - last_scan_at >= scan_interval_sec:
                try:
                    refresh_all_once()
                    last_scan_at = time.time()
                except Exception as exc:  # pragma: no cover
                    with _lock:
                        _set_state(scan_ok=False, message=str(exc))
            time.sleep(intel_interval_sec)

    thread = threading.Thread(target=loop, name="dashboard-refresh", daemon=True)
    thread.start()
    return thread
