#!/usr/bin/env python3
"""
End-to-end UAT for the RADAR → approve → executor pipeline.

Smoke (local, no gh mutations):
  python3 scripts/uat_full_loop.py --smoke

Dry-run (local + read-only gh checks):
  python3 scripts/uat_full_loop.py --dry-run

Verify a specific approved issue and branch:
  python3 scripts/uat_full_loop.py --issue 42

Approve an issue (triggers executor in CI):
  python3 scripts/uat_full_loop.py --approve 42
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DOCS = HERE / "docs"
INDEX = DOCS / "index.json"
RADAR_DIR = DOCS / "radar"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts"))

from draft_issues import parse_findings, validate_issue  # noqa: E402


@dataclass
class StepResult:
    name: str
    status: str  # pass | fail | skip
    detail: str = ""


@dataclass
class UatReport:
    mode: str
    steps: list[StepResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = ""):
        self.steps.append(StepResult(name, status, detail))

    @property
    def ok(self) -> bool:
        return all(s.status in ("pass", "skip") for s in self.steps)

    def to_dict(self):
        return {
            "mode": self.mode,
            "ok": self.ok,
            "steps": [{"name": s.name, "status": s.status, "detail": s.detail} for s in self.steps],
        }


def run_cmd(cmd: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd or HERE,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def gh_available() -> bool:
    proc = run_cmd(["gh", "auth", "status"])
    return proc.returncode == 0


def repo_slug() -> str | None:
    proc = run_cmd(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def step_tests(report: UatReport):
    proc = run_cmd(["python3", "run_tests.py"], timeout=300)
    if proc.returncode == 0:
        report.add("tests", "pass", "run_tests.py green")
    else:
        tail = (proc.stdout or proc.stderr or "")[-800:]
        report.add("tests", "fail", tail)


def step_scan_intel_docgen(report: UatReport, *, refresh: bool):
    if not refresh:
        report.add("scan_intel_docgen", "skip", "use existing docs/index.json")
        return
    env = {**os.environ, "TARGET_REPO": os.environ.get("TARGET_REPO", str(HERE))}
    for label, cmd in (
        ("scan", ["python3", "scan.py"]),
        ("github_intel", ["python3", "scripts/github_intel.py"]),
        ("docgen", ["python3", "docgen.py"]),
    ):
        proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, env=env, timeout=300)
        if proc.returncode != 0:
            report.add("scan_intel_docgen", "fail", f"{label}: {(proc.stderr or proc.stdout)[-500:]}")
            return
    report.add("scan_intel_docgen", "pass", "scan + github_intel + docgen")


def step_radar_report(report: UatReport) -> Path | None:
    if not INDEX.is_file():
        report.add("radar_report", "fail", f"missing {INDEX}")
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        out_path = Path(fh.name)
    proc = run_cmd(["python3", "radar_report.py", "--stdout"], timeout=120)
    if proc.returncode != 0:
        report.add("radar_report", "fail", (proc.stderr or proc.stdout)[-500:])
        return None
    out_path.write_text(proc.stdout)
    if "## " not in proc.stdout or "**Files:**" not in proc.stdout:
        report.add("radar_report", "fail", "report missing required sections")
        return None
    report.add("radar_report", "pass", f"{proc.stdout.count('## ')} finding(s)")
    return out_path


def step_parse_findings(report: UatReport, report_path: Path | None):
    if report_path is None:
        report.add("parse_findings", "skip", "no report")
        return
    try:
        findings = parse_findings(report_path.read_text())
        for item in findings:
            missing = validate_issue(item)
            if missing:
                report.add("parse_findings", "fail", f"{item.get('title')}: missing {missing}")
                return
        report.add("parse_findings", "pass", f"{len(findings)} finding(s) valid for draft_issues")
    finally:
        report_path.unlink(missing_ok=True)


def step_provenance_docgen(report: UatReport):
    modules = DOCS / "modules"
    if not modules.is_dir():
        report.add("provenance_docgen", "skip", "no docs/modules")
        return
    with_prov = [p.name for p in modules.glob("*.md") if "## Provenance" in p.read_text()]
    if with_prov:
        report.add("provenance_docgen", "pass", f"{len(with_prov)} module doc(s) with provenance")
    else:
        index = json.loads(INDEX.read_text()) if INDEX.is_file() else {}
        if index.get("graph", {}).get("edges"):
            report.add("provenance_docgen", "fail", "graph present but no ## Provenance in module docs")
        else:
            report.add("provenance_docgen", "skip", "no provenance graph — run github_intel.py")


def step_graph_delta(report: UatReport, base: str = "main"):
    if not INDEX.is_file():
        report.add("graph_delta", "skip", "no index.json")
        return
    proc = run_cmd(["python3", "scripts/graph_delta.py", "--base", base], timeout=60)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        report.add("graph_delta", "fail", (proc.stdout or proc.stderr)[-500:])
        return
    if proc.returncode == 0:
        report.add("graph_delta", "pass", payload.get("message", "ok"))
    else:
        report.add("graph_delta", "fail", payload.get("message", proc.stderr or "failed"))


def step_gh_auth(report: UatReport):
    if gh_available():
        slug = repo_slug()
        report.add("gh_auth", "pass", slug or "authenticated")
    else:
        report.add("gh_auth", "fail", "run gh auth login")


def step_radar_issues(report: UatReport):
    slug = repo_slug()
    if not slug:
        report.add("radar_issues", "skip", "no gh repo")
        return
    proc = run_cmd(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            slug,
            "--label",
            "radar:proposed,radar:approved",
            "--state",
            "open",
            "--limit",
            "20",
            "--json",
            "number,title,labels",
        ]
    )
    if proc.returncode != 0:
        report.add("radar_issues", "fail", proc.stderr or proc.stdout)
        return
    issues = json.loads(proc.stdout or "[]")
    proposed = sum(1 for i in issues if any(l.get("name") == "radar:proposed" for l in i.get("labels") or []))
    approved = sum(1 for i in issues if any(l.get("name") == "radar:approved" for l in i.get("labels") or []))
    report.add("radar_issues", "pass", f"{len(issues)} open radar issue(s) ({proposed} proposed, {approved} approved)")


def step_issue_view(report: UatReport, issue_num: int):
    slug = repo_slug()
    if not slug:
        report.add("issue_view", "skip", "no gh repo")
        return
    proc = run_cmd(
        ["gh", "issue", "view", str(issue_num), "--repo", slug, "--json", "number,title,labels,state"]
    )
    if proc.returncode != 0:
        report.add("issue_view", "fail", proc.stderr or proc.stdout)
        return
    issue = json.loads(proc.stdout)
    labels = [l.get("name") for l in issue.get("labels") or []]
    detail = f"#{issue_num} {issue.get('title')} [{', '.join(labels)}]"
    if "radar:approved" in labels:
        report.add("issue_view", "pass", detail)
    elif "radar:proposed" in labels:
        report.add("issue_view", "pass", detail + " (proposed — approve to trigger executor)")
    else:
        report.add("issue_view", "fail", detail + " (missing radar:* labels)")


def step_agent_artifacts(report: UatReport, issue_num: int):
    plan = DOCS / "agent-runs" / f"issue-{issue_num}" / "plan.json"
    run = DOCS / "agent-runs" / f"issue-{issue_num}" / "run.json"
    parts = []
    if plan.is_file():
        parts.append("plan.json")
    if run.is_file():
        parts.append("run.json")
    if parts:
        report.add("agent_artifacts", "pass", ", ".join(parts))
    else:
        report.add("agent_artifacts", "skip", f"no docs/agent-runs/issue-{issue_num}/ yet")


def step_issue_branch(report: UatReport, issue_num: int):
    branch = f"issue-{issue_num}"
    run_cmd(["git", "fetch", "origin", branch], timeout=120)
    proc = run_cmd(["git", "rev-parse", "--verify", f"origin/{branch}"])
    if proc.returncode != 0:
        proc = run_cmd(["git", "rev-parse", "--verify", branch])
    if proc.returncode != 0:
        report.add("issue_branch", "skip", f"branch {branch} not found locally or on origin")
        return
    ahead = run_cmd(["git", "rev-list", "--count", f"main..{branch}"])
    count = (ahead.stdout or "0").strip()
    report.add("issue_branch", "pass", f"{branch} exists ({count} commit(s) ahead of main)")


def step_executor_verify(report: UatReport, issue_num: int, base: str = "main"):
    script = HERE / "scripts" / "verify_executor_branch.sh"
    if not script.is_file():
        report.add("executor_verify", "fail", "verify_executor_branch.sh missing")
        return
    branch = f"issue-{issue_num}"
    prior = run_cmd(["git", "branch", "--show-current"])
    prior_branch = (prior.stdout or "main").strip()
    checkout = run_cmd(["git", "checkout", branch])
    if checkout.returncode != 0:
        checkout = run_cmd(["git", "checkout", "-B", branch, f"origin/{branch}"])
    if checkout.returncode != 0:
        report.add("executor_verify", "skip", f"cannot checkout {branch}")
        return
    try:
        proc = run_cmd(["bash", str(script), str(issue_num), base], timeout=600)
        if proc.returncode == 0:
            lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
            report.add("executor_verify", "pass", lines[-1] if lines else "ok")
        else:
            detail = (proc.stderr or proc.stdout or "")[-800:]
            report.add("executor_verify", "fail", detail)
    finally:
        run_cmd(["git", "checkout", prior_branch])


def step_issue_pr(report: UatReport, issue_num: int):
    slug = repo_slug()
    if not slug:
        report.add("issue_pr", "skip", "no gh repo")
        return
    proc = run_cmd(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            slug,
            "--head",
            f"issue-{issue_num}",
            "--json",
            "number,title,state,statusCheckRollup",
        ]
    )
    if proc.returncode != 0:
        report.add("issue_pr", "fail", proc.stderr or proc.stdout)
        return
    prs = json.loads(proc.stdout or "[]")
    if not prs:
        report.add("issue_pr", "skip", f"no PR for issue-{issue_num}")
        return
    pr = prs[0]
    checks = pr.get("statusCheckRollup") or []
    failed = [c for c in checks if (c.get("conclusion") or c.get("state")) in ("FAILURE", "FAILED")]
    detail = f"PR #{pr.get('number')} {pr.get('state')}"
    if failed:
        report.add("issue_pr", "fail", detail + f" — {len(failed)} check(s) failed")
    else:
        report.add("issue_pr", "pass", detail)


def approve_issue(issue_num: int) -> tuple[bool, str]:
    slug = repo_slug()
    if not slug:
        return False, "gh repo unavailable"
    proc = run_cmd(
        [
            "gh",
            "issue",
            "edit",
            str(issue_num),
            "--repo",
            slug,
            "--add-label",
            "radar:approved",
            "--remove-label",
            "radar:proposed",
        ]
    )
    if proc.returncode != 0:
        return False, proc.stderr or proc.stdout
    return True, f"labeled #{issue_num} radar:approved (executor workflow will trigger in CI)"


def run_smoke(refresh: bool = False) -> UatReport:
    report = UatReport("smoke")
    step_tests(report)
    if report.ok:
        step_scan_intel_docgen(report, refresh=refresh)
    if report.ok:
        radar_path = step_radar_report(report)
        step_parse_findings(report, radar_path)
        step_provenance_docgen(report)
        step_graph_delta(report)
    return report


def run_dry_run(refresh: bool = False) -> UatReport:
    report = run_smoke(refresh=refresh)
    report.mode = "dry-run"
    if report.ok:
        step_gh_auth(report)
    if report.ok:
        step_radar_issues(report)
    return report


def run_issue_uat(issue_num: int, *, verify_branch: bool = False) -> UatReport:
    report = run_dry_run(refresh=False)
    report.mode = f"issue-{issue_num}"
    if report.ok:
        step_issue_view(report, issue_num)
        step_agent_artifacts(report, issue_num)
        step_issue_branch(report, issue_num)
        step_issue_pr(report, issue_num)
    if verify_branch and report.ok:
        step_executor_verify(report, issue_num)
    return report


def print_report(report: UatReport, as_json: bool):
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return
    print(f"UAT mode: {report.mode}")
    for step in report.steps:
        icon = {"pass": "✓", "fail": "✗", "skip": "○"}.get(step.status, "?")
        line = f"  {icon} {step.name}: {step.status}"
        if step.detail:
            line += f" — {step.detail}"
        print(line)
    print(f"\n{'PASS' if report.ok else 'FAIL'}")


def main():
    parser = argparse.ArgumentParser(description="RADAR → approve → executor UAT ladder")
    parser.add_argument("--smoke", action="store_true", help="local pipeline only (default)")
    parser.add_argument("--dry-run", action="store_true", help="smoke + read-only gh checks")
    parser.add_argument("--issue", type=int, metavar="N", help="verify issue #N pipeline artifacts")
    parser.add_argument("--verify-branch", action="store_true", help="with --issue: run verify_executor_branch.sh")
    parser.add_argument("--approve", type=int, metavar="N", help="add radar:approved to issue #N (triggers CI)")
    parser.add_argument("--refresh", action="store_true", help="re-run scan + github_intel + docgen first")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.approve:
        ok, msg = approve_issue(args.approve)
        print(msg)
        if not ok:
            raise SystemExit(1)
        print(f"Next: gh run list --workflow=executor.yml --limit 3")
        print(f"Then: python3 scripts/uat_full_loop.py --issue {args.approve}")
        raise SystemExit(0)

    if args.issue:
        report = run_issue_uat(args.issue, verify_branch=args.verify_branch)
    elif args.dry_run:
        report = run_dry_run(refresh=args.refresh)
    else:
        report = run_smoke(refresh=args.refresh)

    print_report(report, args.json)
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
