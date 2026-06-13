# repo-intel operator runbook

Day-to-day commands for the ticket-sys checkout.

## First-time setup

```bash
cp .env.example .env
# TARGET_REPO = project you monitor (e.g. hhl_site)
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

See also `docs/inspiration.md` and `AGENTS.md`.
