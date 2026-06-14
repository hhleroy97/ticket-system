# repo-intel

Set `TARGET_REPO` to a local git repo path, then build the dashboard.
The scanner is deterministic and stdlib-only (no pip installs, no LLM calls).

```bash
cp .env.example .env        # edit TARGET_REPO
python3 scan.py             # writes docs/index.json, docs/index.db, docs/dashboard.html
python3 scripts/github_intel.py   # optional; merges last 30 merged PRs + radar issues (needs gh auth)
python3 docgen.py             # writes docs/modules/*.md from the index
python3 radar_report.py       # writes docs/radar/<date>.md from the index
open docs/dashboard.html      # xdg-open on Linux

# Local dashboard with Cursor chat (127.0.0.1 only)
python3 serve_dashboard.py    # http://127.0.0.1:8765 — auto git sync every 60s
```

Or point it at a repo inline:

```bash
TARGET_REPO=/path/to/repo python3 scan.py
```

## Index contract

`docs/index.json` is the single source of truth for the dashboard and downstream tooling.
Schema **v2** adds optional `pull_requests`, `issues`, `github`, `open_pull_requests`,
`workflow_runs`, and `pipeline` sections (populated by `scripts/github_intel.py`). The
`pipeline` object maps each open RADAR ticket to a stage (`proposed` → `approved` →
`implementing` → `pr_open` → `ci`) and may include `agent_run` git introspection from
`docs/agent-runs/issue-N/run.json`. Prefer additive schema changes; bump `schema_version`
when you must break compatibility (see HANDOFF.md for the full schema). The `package_roots` field maps
Python package prefixes to directories (e.g. `{"": "src"}` for src-layout); it is `{}` when
the scanned repo has no detected roots.

The dashboard shows a **PR timeline** (linked to issues via `Closes #N` / `issue-N` branches),
**ticket pipeline** (stage graph: proposed → approved → agent → PR → CI), **agent run traces**
(`docs/agent-runs/issue-N/run.json` from the executor), **ticket list** for open `radar:*` issues
(with **Approve** via local server), **live workflow polling** (including step-level detail for
in-progress runs), and **auto-refresh** of tickets/PRs (~15s) when using `serve_dashboard.py`.
**Cursor chat** and ticket approval run only locally — not on GitHub Pages.

## Contributing (PR workflow)

All maintainer and agent edits use **pull requests** — never direct pushes to `main`:

```bash
git checkout main && ./hooks/sync-origin-main.sh
git checkout -b feat/my-change
# … edit, commit logically …
python3 run_tests.py
git push -u origin HEAD
gh pr create --title "feat: …" --body "## Summary\n…\n\n## Test plan\n- [x] python3 run_tests.py"
```

Merge after `test.yml` passes. Regenerated `docs/*` from a local scan belong in the same PR
(or a follow-up `docs:` PR) — not a direct push to `main`.

Scheduled **RADAR** and **scan-and-docs** jobs still push generated docs to `main` via
`push_to_main.sh` (bot exception). Executor tickets always land as `issue-<N>` PRs.

## Roadmap

See **`docs/KNOWLEDGE_GRAPH_PLAN.md`** for the git-provenance knowledge graph vision
(commits, PRs, CI runs on a navigable force graph; multi-repo analysis via `TARGET_REPO`).

## Layout

```
repo-intel/
├── scan.py                     # deterministic scanner (Phase 0–1)
├── docgen.py                   # deterministic module doc generator (Phase 2)
├── radar_report.py             # deterministic RADAR findings from index.json
├── draft_issues.py             # parse RADAR markdown → issue JSON
├── serve_dashboard.py          # local HTTP server + Cursor chat API
├── scripts/github_intel.py     # merge GitHub PR/issue metadata into index.json
├── scripts/pipeline_lib.py     # ticket pipeline stages + agent-run introspection
├── scripts/finalize_agent_run.py  # post-agent git capture for executor branches
├── scripts/run_executor_agent.sh  # cursor-agent wrapper with progress snapshots
├── run_tests.py                # unittest entrypoint
├── templates/dashboard.html.tmpl
├── docs/                       # generated artifacts + radar findings
├── hooks/pre-commit            # optional: scan + docgen on commit
├── .github/workflows/          # scan, RADAR, tickets, executor, pages, test
├── AGENTS.md                   # Cursor model routing rules
└── HANDOFF.md                  # full build plan
```

## Workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `test.yml` | push/PR | Runs `run_tests.py` |
| `auto-merge.yml` | after `test` on PRs | Merges safe `bot/*` docs PRs and low-risk `issue-*` PRs |
| `resolve-conflicts.yml` | push to `main`, cron, manual | Merges `main` into open PRs; auto-fixes doc-only conflicts |
| `scan-and-docs.yml` | daily cron + non-docs pushes | Rescan + docgen → **direct push to main** |
| `radar.yml` | weekly cron | Scan → report → push to main → **draft issues in same job** |
| `radar-tickets.yml` | manual push to `main` (`docs/radar/*.md`) | Same drafting when RADAR md changes outside `radar.yml` |
| `executor.yml` | issue labeled `radar:approved` | Composer 2.5, logical commits, agent-run trace, PR (`Closes #N`) |
| `pages.yml` | push to main | Publishes `docs/` to GitHub Pages |

**Autonomy:** RADAR and scan/docs **push straight to `main`** (no bot PRs → no “Approve workflow run”). Low-risk executor PRs **auto-merge with `--admin`** after tests pass in the job. Close stale open bot PRs (#13 etc.) manually.

Set repository secret `CURSOR_API_KEY` for executor workflows.

**If executor PRs still ask to approve workflows:** Repo **Settings → Actions → General → Fork pull request workflows** → disable “Require approval for all outside collaborators”.

Optional git hooks (scan refresh + stay synced with origin/main):

```bash
./hooks/install.sh              # sets git config core.hooksPath hooks (once per clone)
./hooks/sync-origin-main.sh     # fetch + fast-forward main (also switches to main if clean)
```

| Hook | When | Effect |
| --- | --- | --- |
| `pre-commit` | commit | Rescan when scanner inputs change |
| `post-merge` | `git pull` / merge on main | fetch + fast-forward `main` |
| `post-checkout` | switch to `main` | same sync |

After merging a PR on GitHub (web UI), run `./hooks/sync-origin-main.sh` locally — hooks only fire on local git commands.

Cursor also runs sync after `gh pr merge`, `git pull`, or `git checkout main` (see `.cursor/hooks.json`).

**Executor PRs:** merge with **Rebase and merge** or **Merge commit** (not squash) to keep logical commits on `main`.

## Research notes

GitHits was unavailable in this environment (auth required). Similar OSS patterns consulted:

- [netimport](https://github.com/beilak/netimport) — pyproject-driven import analysis
- [scaffoldr](https://github.com/sepiabrown/scaffoldr) — workspace/package discovery
- [Cursor CLI in GitHub Actions](https://cursor.com/docs/cli/github-actions) — headless agent patterns

See HANDOFF.md for the full build plan and AGENTS.md for Cursor model-routing rules.
