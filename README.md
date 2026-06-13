# repo-intel

Set `TARGET_REPO` to a local git repo path, then build the dashboard.
The scanner is deterministic and stdlib-only (no pip installs, no LLM calls).

```bash
cp .env.example .env        # edit TARGET_REPO
python3 scan.py             # writes docs/index.json, docs/index.db, docs/dashboard.html
python3 docgen.py             # writes docs/modules/*.md from the index
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
| `scan-and-docs.yml` | push to main | Rescan + module docs PR |
| `radar.yml` | weekly cron | Auto research → `docs/radar/` PR |
| `radar-tickets.yml` | RADAR PR merged | Opens `radar:proposed` issues |
| `executor.yml` | issue labeled `radar:approved` | Composer 2.5 implements + opens PR |
| `pages.yml` | push to main | Publishes `docs/` to GitHub Pages |

Set repository secret `CURSOR_API_KEY` for agent workflows.

Optional git hooks (scan refresh + stay synced with origin/main):

```bash
git config core.hooksPath hooks
```

| Hook | When | Effect |
| --- | --- | --- |
| `pre-commit` | commit | Rescan when scanner inputs change |
| `post-merge` | `git pull` / merge on main | `git fetch` + fast-forward `main` from `origin/main` |
| `post-checkout` | switch to `main` | same sync (useful after merging/closing a PR locally) |

Manual sync anytime:

```bash
./hooks/sync-origin-main.sh
```

Cursor also runs the sync after `gh pr merge|close` or `git checkout main` (see `.cursor/hooks.json`).

## Research notes

GitHits was unavailable in this environment (auth required). Similar OSS patterns consulted:

- [netimport](https://github.com/beilak/netimport) — pyproject-driven import analysis
- [scaffoldr](https://github.com/sepiabrown/scaffoldr) — workspace/package discovery
- [Cursor CLI in GitHub Actions](https://cursor.com/docs/cli/github-actions) — headless agent patterns

See HANDOFF.md for the full build plan and AGENTS.md for Cursor model-routing rules.
