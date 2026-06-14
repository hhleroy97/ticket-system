#!/usr/bin/env python3
"""
Local dashboard server with Cursor chat, ticket approval, and workflow polling.

Serves docs/ on http://127.0.0.1:8765
Requires gh auth for approve/workflows; CURSOR_API_KEY for chat.
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"
INDEX = DOCS / "index.json"
TEMPLATE = HERE / "templates" / "dashboard.html.tmpl"
PORT = int(os.environ.get("DASHBOARD_PORT", "8765"))
HOST = "127.0.0.1"

sys.path.insert(0, str(HERE / "scripts"))

from dashboard_api import (  # noqa: E402
    approve_issue,
    fetch_radar_issues,
    fetch_workflow_run_detail,
    fetch_workflow_runs,
    gh_available,
    parse_api_path,
    query_reach,
    repo_slug,
)
from repo_sync import get_state, start_background_sync, sync_once  # noqa: E402
from dashboard_refresh import (  # noqa: E402
    get_refresh_state,
    read_index_payload,
    refresh_all_once,
    refresh_intel_once,
    start_background_refresh,
)

SYNC_INTERVAL_SEC = int(os.environ.get("SYNC_INTERVAL_SEC", "60"))
REFRESH_INTERVAL_SEC = int(os.environ.get("REFRESH_INTERVAL_SEC", "15"))
SCAN_INTERVAL_SEC = int(os.environ.get("SCAN_INTERVAL_SEC", "90"))
POLL_ISSUES_MS = int(os.environ.get("POLL_ISSUES_MS", "10000"))
POLL_WORKFLOWS_MS = int(os.environ.get("POLL_WORKFLOWS_MS", "4000"))
POLL_INDEX_MS = int(os.environ.get("POLL_INDEX_MS", "10000"))


def load_dotenv():
    env_path = HERE / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def build_local_dashboard():
    if not INDEX.is_file():
        raise SystemExit("error: missing docs/index.json — run scan.py first")
    index = json.loads(INDEX.read_text())
    index.setdefault("meta", {})
    index["meta"]["local_chat"] = True
    index["meta"]["local_actions"] = True
    index["meta"]["poll_ms"] = {
        "index": POLL_INDEX_MS,
        "issues": POLL_ISSUES_MS,
        "workflows": POLL_WORKFLOWS_MS,
        "sync": min(SYNC_INTERVAL_SEC * 1000, 15000),
    }
    tmpl = TEMPLATE.read_text()
    return tmpl.replace("/*__DATA__*/", json.dumps(index))


def summarize_context():
    if not INDEX.is_file():
        return "No index.json available."
    index = json.loads(INDEX.read_text())
    repo = index.get("repo", {})
    stats = index.get("stats", {})
    lines = [
        f"Repo: {repo.get('name')} @ {repo.get('head')} ({repo.get('branch')})",
        f"Stats: {stats.get('file_count')} files, {stats.get('edge_count')} import edges",
    ]
    prs = index.get("pull_requests") or []
    if prs:
        lines.append("Recent merged PRs:")
        for pr in prs[:10]:
            issues = ", ".join(f"#{n}" for n in pr.get("issue_numbers") or []) or "none"
            lines.append(f"  PR #{pr.get('number')}: {pr.get('title')} (issues: {issues})")
    issues = index.get("issues") or []
    if issues:
        lines.append("Open radar issues:")
        for issue in issues[:10]:
            labels = ", ".join(issue.get("labels") or [])
            stage = issue.get("stage_label") or issue.get("stage") or ""
            stage_bit = f" ({stage})" if stage else ""
            lines.append(f"  #{issue.get('number')}: {issue.get('title')} [{labels}]{stage_bit}")
    pipeline = index.get("pipeline") or {}
    tickets = pipeline.get("tickets") or []
    if tickets:
        lines.append("Pipeline stages:")
        for ticket in tickets[:10]:
            agent = ticket.get("agent_run") or {}
            commits = agent.get("commit_count") or len(agent.get("commits") or [])
            lines.append(
                f"  #{ticket.get('issue_number')}: {ticket.get('stage_label')} "
                f"({commits} agent commit(s))"
            )
    return "\n".join(lines)


def run_cursor_chat(message):
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        return None, "CURSOR_API_KEY not set in .env or environment"

    context = summarize_context()
    prompt = (
        "You are helping the user understand their repo-intel dashboard data. "
        "Answer concisely using the context below. If unsure, say so.\n\n"
        f"--- context ---\n{context}\n--- end context ---\n\n"
        f"User question: {message}"
    )
    proc = subprocess.run(
        ["cursor-agent", "-p", "--model", "composer-2.5", prompt],
        capture_output=True,
        text=True,
        env={**os.environ, "CURSOR_API_KEY": api_key},
        timeout=300,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "cursor-agent failed").strip()
        return None, err[:2000]
    reply = (proc.stdout or "").strip()
    return reply or "(empty response)", None


class DashboardHandler(BaseHTTPRequestHandler):
    local_html = None

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _require_gh(self):
        if not gh_available():
            self._send_json(503, {"error": "gh not authenticated — run gh auth login"})
            return False
        slug = repo_slug()
        if not slug:
            self._send_json(503, {"error": "could not resolve GitHub repo"})
            return False
        return slug

    def do_GET(self):
        path = urlparse(self.path).path
        resource, resource_id = parse_api_path(path, "GET")

        if resource == "workflows":
            slug = self._require_gh()
            if not slug:
                return
            runs, err = fetch_workflow_runs(slug)
            if err:
                self._send_json(500, {"error": err})
                return
            self._send_json(200, {"runs": runs})
            return

        if resource == "workflow_run":
            slug = self._require_gh()
            if not slug:
                return
            detail, err = fetch_workflow_run_detail(slug, resource_id)
            if err:
                self._send_json(500, {"error": err})
                return
            self._send_json(200, detail)
            return

        if resource == "issues":
            slug = self._require_gh()
            if not slug:
                return
            issues, err = fetch_radar_issues(slug)
            if err:
                self._send_json(500, {"error": err})
                return
            self._send_json(200, {"issues": issues})
            return

        if resource == "reach":
            qs = parse_qs(urlparse(self.path).query)
            file_path = (qs.get("from") or [""])[0].strip()
            if not file_path:
                self._send_json(400, {"error": "query param 'from' required"})
                return
            try:
                depth = int((qs.get("depth") or ["2"])[0])
            except ValueError:
                depth = 2
            self._send_json(200, query_reach(file_path, depth=depth))
            return

        if path == "/api/sync":
            self._send_json(200, get_state())
            return

        if path == "/api/index":
            payload = read_index_payload()
            payload["refresh"] = get_refresh_state()
            self._send_json(200, payload)
            return

        if path in ("/", "/dashboard.html"):
            html = self.local_html or build_local_dashboard()
            self._send_bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return

        rel = path.lstrip("/")
        target = (DOCS / rel).resolve()
        if not str(target).startswith(str(DOCS.resolve())) or not target.is_file():
            self.send_error(404)
            return
        content_type = "application/octet-stream"
        if target.suffix == ".json":
            content_type = "application/json"
        elif target.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        self._send_bytes(200, target.read_bytes(), content_type)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/chat":
            try:
                payload = self._read_json_body()
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid JSON"})
                return
            message = (payload.get("message") or "").strip()
            if not message:
                self._send_json(400, {"error": "message required"})
                return
            reply, err = run_cursor_chat(message)
            if err:
                self._send_json(500, {"error": err})
                return
            self._send_json(200, {"reply": reply})
            return

        resource, issue_number = parse_api_path(path, "POST")
        if resource == "approve":
            slug = self._require_gh()
            if not slug:
                return
            try:
                payload = self._read_json_body()
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid JSON"})
                return
            auto_merge = bool(payload.get("auto_merge"))
            result, err = approve_issue(slug, issue_number, auto_merge=auto_merge)
            if err:
                self._send_json(500, {"error": err})
                return
            self._send_json(200, result)
            return

        if path == "/api/sync":
            state = sync_once(stay=True)
            refresh_intel_once()
            state["index"] = read_index_payload()
            self._send_json(200, state)
            return

        if path == "/api/refresh":
            ok, msg = refresh_all_once()
            self._send_json(200, {"ok": ok, "message": msg, "index": read_index_payload()})
            return

        self.send_error(404)


def main():
    load_dotenv()
    if not DOCS.is_dir():
        sys.exit("error: docs/ missing — run scan.py first")
    if not INDEX.is_file():
        sys.exit("error: missing docs/index.json — run scan.py first")
    DashboardHandler.local_html = build_local_dashboard()
    sync_once(stay=True)
    refresh_intel_once()
    start_background_sync(interval_sec=SYNC_INTERVAL_SEC, stay=True)
    start_background_refresh(
        intel_interval_sec=REFRESH_INTERVAL_SEC,
        scan_interval_sec=SCAN_INTERVAL_SEC,
    )
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"repo-intel dashboard: http://{HOST}:{PORT}/")
    print(f"Git sync: every {SYNC_INTERVAL_SEC}s | GitHub intel: every {REFRESH_INTERVAL_SEC}s | scan: every {SCAN_INTERVAL_SEC}s")
    print(f"UI polls index every {POLL_INDEX_MS}ms · workflows every {POLL_WORKFLOWS_MS}ms")
    print("Local API: approve tickets, poll workflows (gh auth), chat (CURSOR_API_KEY).")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
