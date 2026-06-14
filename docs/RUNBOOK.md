# repo-intel operator runbook

Day-to-day commands for the ticket-sys checkout.

## First-time setup

```bash
cp .env.example .env
# TARGET_REPO defaults to this repo; override to monitor another project (e.g. hhl_site)
# CURSOR_API_KEY = for local chat + CI executor
gh auth login
./hooks/install.sh   # optional pre-commit
```

## Scan & dashboard

```bash
# Scan monitored repo → writes ticket-sys/docs/*
TARGET_REPO=~/projects/personal/hhl_site python3 scan.py
python3 scripts/github_intel.py

# Local dashboard (approve tickets, workflows, pipeline, chat)
python3 serve_dashboard.py   # http://127.0.0.1:8765
```

**Important:** Pre-commit hooks always scan **this repo** (ticket-sys), not `TARGET_REPO`.
Background refresh uses `TARGET_REPO` for the module graph.

## Ticket pipeline

| Stage | Meaning |
| --- | --- |
| Proposed | `radar:proposed` — needs approval |
| Approved | `radar:approved` — executor will trigger |
| Agent working | executor workflow running on `issue-N` |
| PR open / CI | Linked PR; tests running |
| Merged | PR merged, issue closed |

Approve from dashboard (**Approve** button) or:

```bash
gh issue edit N --add-label radar:approved --remove-label radar:proposed
```

Low-risk: check **auto-merge** in UI or add `radar:auto-merge`.

## Agent traces

During executor runs:

- `docs/agent-runs/issue-N/plan.json` — pre-implementation plan (Auto model)
- `docs/agent-runs/issue-N/run.json` — commits/files snapshots every 30s
- GitHub issue comments — throttled progress posts

## Git workflow (maintainers)

```bash
git checkout main && ./hooks/sync-origin-main.sh
git checkout -b feat/my-change
python3 run_tests.py
git push -u origin HEAD
gh pr create --title "feat: …" --body "…"
# merge after test.yml green
```

## Merge conflict bot

Workflow **resolve-conflicts** runs when `main` moves, every 6 hours, or manually:

```bash
gh workflow run resolve-conflicts.yml
gh workflow run resolve-conflicts.yml -f pr=36 -f dry_run=true   # assess only
```

For each open same-repo PR it:

1. **Assesses** merge status (`MERGEABLE`, `CONFLICTING`, `BEHIND`, fork/draft skips).
2. **Fixes** by merging `origin/main` into the PR branch.
3. **Auto-resolves** doc-only conflicts (`docs/index.json`, dashboard, module docs) via scan + github_intel.
4. **Scoped agent** — for code conflicts, runs Composer 2.5 with `.github/CONFLICT_RESOLVER.md`
   (only conflicted paths, max 12 files, no workflow edits); runs tests before push.
5. **Comments** on the PR; trace at `docs/agent-runs/pr-<N>/run.json`.

Requires `CURSOR_API_KEY` secret for semantic resolution. Fork PRs and workflow conflicts are never auto-edited.

```bash
gh workflow run resolve-conflicts.yml -f no_agent=true   # doc-only mode
```

## Parallel development (worktrees)

```bash
git worktree add ../ticket-sys-wt/feature -b feat/name main
# work in ../ticket-sys-wt/feature, push, PR, remove when done
git worktree remove ../ticket-sys-wt/feature
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Wrong repo in `docs/index.json` after commit | Pre-commit now forces `TARGET_REPO=$ROOT`; re-run scan with explicit `TARGET_REPO` |
| Dashboard workflows 500 | Ensure `gh auth login`; check `gh run list` JSON fields |
| Executor doesn’t start | Issue needs `radar:approved` label event; re-add label to retrigger |
| Pages missing live features | Use `serve_dashboard.py`, not static `file://` |

## Full loop UAT (RADAR → approve → executor)

Automated ladder in `scripts/uat_full_loop.py`:

```bash
# 1. Local pipeline (tests, RADAR report, draft_issues parse, graph_delta)
python3 scripts/uat_full_loop.py --smoke

# 2. Smoke + read-only GitHub checks (gh auth, open radar issues)
python3 scripts/uat_full_loop.py --dry-run

# 3. Re-scan before smoke (optional)
python3 scripts/uat_full_loop.py --smoke --refresh

# 4. Approve an issue — triggers executor workflow in CI
python3 scripts/uat_full_loop.py --approve N

# 5. After executor runs: verify issue artifacts, branch, PR
python3 scripts/uat_full_loop.py --issue N

# 6. If issue-N branch exists locally: run verify_executor_branch.sh
python3 scripts/uat_full_loop.py --issue N --verify-branch
```

**Manual approval** (same as dashboard Approve button):

```bash
gh issue edit N --add-label radar:approved --remove-label radar:proposed
gh run list --workflow=executor.yml --limit 3
```

**Pass criteria for a full loop:**

| Step | Check |
| --- | --- |
| RADAR | `docs/radar/YYYY-MM-DD.md` sections parse via `draft_issues.py` |
| Approve | Issue has `radar:approved`; executor workflow starts |
| Agent | `docs/agent-runs/issue-N/plan.json` and `run.json` appear |
| Verify | `verify_executor_branch.sh` passes (tests + graph_delta) |
| PR | PR from `issue-N` branch opens; CI green |

Use a **low-risk** finding (docs/tests only) with `radar:auto-merge` for the first live run.

## Self-improving loop (operator requests)

Your approve/dismiss actions and explicit requests steer the next RADAR cycle.

**Feedback log:** `docs/operator-feedback.jsonl` (append-only JSON lines)

| Action | When |
| --- | --- |
| `request_created` | Dashboard **Ticket** or `scripts/request_issue.py` |
| `approved` | Dashboard **Approve** or `gh issue edit … radar:approved` |
| `dismissed` | Dashboard **Dismiss** (closes issue + logs) |
| `ci_failed` | `reflect_cycle` after `github_intel` sees failed test/executor run |
| `ci_passed` | Successful test workflow on an issue branch |
| `blast_radius_miss` | Agent touched files outside executor plan reach set |

After **two dismissals** of similar finding titles, RADAR stops proposing that theme. Approved themes rank higher in `create_radar_issues.py`. **CI failures** and **blast-radius misses** lower a theme's score; **ci_passed** nudges it up.

```bash
# Create issue from your request (radar:proposed + radar:request)
python3 scripts/request_issue.py "Add KG-14 author edges" --acceptance "Author nodes in graph"

# Dashboard: type request → click Ticket (or Send for chat only)
# Dismiss noisy RADAR tickets to teach deprioritization

# Manual reflection pass (also runs at end of github_intel.py)
python3 scripts/reflect_cycle.py
```

**Dashboard:** select a pipeline ticket to open the **CI spine** (issue → runs → steps → files). Toggle **Operations** on the graph to highlight step coverage. The **Learning** panel shows recent feedback entries.

See also `docs/inspiration.md`, `docs/KNOWLEDGE_GRAPH_PLAN.md`, and `AGENTS.md`.
