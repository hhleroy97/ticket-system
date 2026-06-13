# repo-intel

Set `TARGET_REPO` to a local git repo path, then build the dashboard.
The scanner is deterministic and stdlib-only (no pip installs, no LLM calls).

```bash
cp .env.example .env        # edit TARGET_REPO
python3 scan.py             # writes docs/index.json, docs/index.db, docs/dashboard.html
python3 docgen.py             # writes docs/modules/*.md from the index
python3 radar_report.py       # writes docs/radar/<date>.md from the index
open docs/dashboard.html      # xdg-open on Linux
```

Or point it at a repo inline:

```bash
TARGET_REPO=/path/to/repo python3 scan.py
```

## Index contract

`docs/index.json` is the single source of truth for the dashboard and downstream tooling.
Prefer additive schema changes; bump `schema_version` when you must break compatibility
(see HANDOFF.md for the full schema). The `package_roots` field maps Python package prefixes
to directories (e.g. `{"": "src"}` for src-layout); it is `{}` when the scanned repo has no
detected roots.

## Layout

```
repo-intel/
├── scan.py                     # deterministic scanner (Phase 0–1)
├── docgen.py                   # deterministic module doc generator (Phase 2)
├── radar_report.py             # deterministic RADAR findings from index.json
├── draft_issues.py             # parse RADAR markdown → issue JSON
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
| `scan-and-docs.yml` | daily cron + non-docs pushes | Rescan + docgen → **direct push to main** |
| `radar.yml` | weekly cron | `scan.py` + `radar_report.py` → **direct push to main** |
| `radar-tickets.yml` | push to `main` (`docs/radar/*.md`) | Deterministic issues (dedup, cap 3, auto-approve low risk) |
| `executor.yml` | issue labeled `radar:approved` | Composer 2.5, logical commits, PR (`Closes #N`) |
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
