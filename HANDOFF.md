# repo-intel — Build Handoff

A greenfield repository-intelligence devops tool. It scans a target git repo, makes its
structure visible (state dashboard + dependency knowledge graph), keeps docs current via
hooks, runs a research loop, and drafts/executes tickets through a human-gated pipeline.

This document is written to be handed directly to a coding agent (Cursor CLI). Phase 0 is
already built and tested — start at Phase 1.

---

## Goal

Turn any git repo into a live, queryable picture of itself, and close the loop so that
findings become tickets and tickets become PRs — at near-zero fixed cost, with the only
metered spend routed through a Cursor subscription rather than a separate Anthropic key.

## Hard constraints (do not violate)

1. **Greenfield and self-contained.** No dependency on any other project or private package.
   Everything lives in this one repo.
2. **GitHub is the backbone.** Storage = repo, orchestration = Actions (cron + events),
   ticket queue = Issues, hosting = Pages. Do not stand up servers, databases-as-a-service,
   or paid hosting.
3. **The scanner is deterministic and agent-free.** Scanning/indexing must be reproducible
   and cost nothing. Never call an LLM to produce the index. Agents are used only for
   reasoning tasks (research, drafting, executing).
4. **All agent work goes through the Cursor CLI**, headless, billed to the Cursor
   subscription. No Anthropic API key anywhere. See "Cursor CLI usage" below.
5. **Human-in-the-loop gate before any code is executed.** No issue is acted on until a
   human approves it (label-based).

## Current status — beyond Phase 0 (implemented)

Phases 1–6 are largely built in this repo:

- **Scanner** with package roots, SQLite, deduped `git ls-files`, optional external `TARGET_REPO`
- **docgen**, **RADAR** (deterministic `radar_report.py`), **ticket drafting**, **executor** with agent traces
- **Local dashboard** (`serve_dashboard.py`): pipeline stages, PR/issue intel, workflow steps, approve, chat
- **GitHub Pages** via `pages.yml`; maintainer changes go through **PRs** (see AGENTS.md)

Start new work from `docs/RUNBOOK.md` and `docs/inspiration.md`. HANDOFF build plan below remains the original spec reference.

## Current status — Phase 0 (DONE, tested)

Built and validated against a real repo (`pallets/click`, 3,242 commits, 63 Python files):

- `scan.py` — walks a git repo via `git ls-files`, classifies files by language, counts
  LOC, pulls per-file churn + last-commit date from a single `git log` pass, builds an
  **import dependency graph** (Python via `ast`, JS/TS via regex), and writes
  `docs/index.json` + a standalone `docs/dashboard.html`.
- `templates/dashboard.html.tmpl` — the UI. Force-directed module graph (node size = LOC,
  color = commit activity cool→hot, edges = imports) + state cards + language composition +
  most-active-files. Data is inlined at build time, so the dashboard opens with no server.
- Verified: import edges resolve to real internal modules; churn correctly flags `core.py`
  as the hotspot; the dashboard builds with data injected and is well-formed.

Run it:

```bash
TARGET_REPO=/path/to/any/git/repo python3 scan.py
open docs/dashboard.html        # macOS;  xdg-open on Linux
```

## Repo layout

```
repo-intel/
├── scan.py                     # deterministic scanner (Phase 0, done)
├── templates/
│   └── dashboard.html.tmpl      # UI template, /*__DATA__*/ token injected by scan.py
├── docs/
│   ├── index.json               # generated: repo state + graph (source of truth for UI/RADAR)
│   └── dashboard.html           # generated: standalone visualization
├── .env.example                 # TARGET_REPO=...
├── AGENTS.md                    # rules read by Cursor (editor + headless) — model routing
├── .github/workflows/           # Phases 2–5 (to build)
└── README.md
```

## Configuration

Single knob for now. Resolution order in `scan.py`: `TARGET_REPO` env var → `TARGET_REPO=`
line in `.env` → demo fallback (`./test-repos/click`). Copy `.env.example` to `.env` and set
`TARGET_REPO` to a local repo path to point it at your own code.

## index.json schema (the contract — UI and RADAR both read this)

```jsonc
{
  "schema_version": 1,
  "repo":   { "name", "path", "branch", "head", "total_commits", "generated_at" },
  "package_roots": { "<prefix>": "<dir>" },  // e.g. {"": "src"} for src-layout; {} when none
  "stats":  { "file_count", "total_loc", "contributor_count", "edge_count" },
  "languages": [ { "name", "files", "loc" } ],
  "files":  [ { "path", "lang", "loc", "size", "commits", "last_commit" } ],
  "edges":  [ { "source": "<path>", "target": "<path>" } ]   // internal imports only
}
```

`package_roots` maps a logical Python package prefix to a filesystem directory under the
repo root. An empty-string prefix (`""`) means top-level imports resolve under that
directory (setuptools `package-dir`, `packages.find.where`, `setup.py` `package_dir`, or
a `src/` tree with tracked `__init__.py` packages). Non-empty prefixes map namespaced
packages (e.g. `"mypkg": "lib/mypkg"`). Flat layouts with no detected roots emit `{}`.
Import edges use these aliases so `from mypkg.core import …` resolves in src-layout repos.

Keep this schema stable. Anything downstream (dashboard, RADAR prompts, ticket drafts)
depends on it. Additive changes only; bump a `schema_version` field if you must break it.

---

## Cursor CLI usage (read before building Phases 3–5)

All agent invocations are headless via `cursor-agent -p`. Auth in CI is the `CURSOR_API_KEY`
secret (interactive `cursor-agent login` won't work in Actions). The CLI reads `AGENTS.md`,
`.cursor/rules`, and `mcp.json` from the repo root — same config as the editor.

**Model routing (this is the cost strategy — do not select frontier models in automation):**

| Task | Model | Why |
|---|---|---|
| Executor (edit files, run tests, open PR) | `composer-2.5` | Cursor's agentic-coding model; benchmark-competitive with frontier on coding at ~1/10 cost; draws the *included* pool, not metered API credits. |
| Research / synthesis / ticket drafting | `auto` | General reasoning, not coding. Auto also draws the included pool and keeps running after it's spent. |
| Anything | never a named frontier model | Selecting Claude/GPT bills the metered $20 API pool at full rate. |

Confirm the exact model slug with `cursor-agent --help` before baking it in — the identifier
string drifts between CLI versions. Prefer the standard (non-Fast) Composer tier for
unattended runs where latency doesn't matter, to stretch the included pool. **Set a spend
limit in Settings → Billing** before pointing cron at it — unattended overage bills silently.

Invocation patterns:

```bash
export CURSOR_API_KEY=$CURSOR_API_KEY

# research / drafting (Auto, JSON out for parsing)
cursor-agent -p --model auto --output-format json \
  "Read docs/index.json. Identify modules with high churn and no recent docs update. \
   Output a JSON array of {title, body, rationale}."

# executor (Composer 2.5, allowed to write)
cursor-agent -p --force --model composer-2.5 \
  "Implement the change in GitHub issue #$ISSUE. Run the test suite. Keep the diff minimal."
```

---

## Build plan

### Phase 1 — scanner hardening
- **Package-root resolution.** Current import resolution maps modules by file path, so a
  `src/` layout makes top-level imports (`import click`) miss. Detect package roots
  (`src/`, presence of `pyproject.toml`/`setup.py`, `package.json` `main`/`exports`) and
  resolve against them. This is the known gap from Phase 0.
- Optional SQLite output (`docs/index.db`) alongside JSON for analytical queries over scan
  history; JSON stays the UI contract.
- Broaden import parsing: Python `importlib`/dynamic imports best-effort; TS path aliases
  from `tsconfig.json`.
- Acceptance: on a `src/`-layout repo, test files that `import <pkg>` produce edges to the
  package; node-participation count rises accordingly.

### Phase 2 — auto-doc hooks
- A `pre-commit` hook (and a mirror GitHub Action on push) that re-runs `scan.py` and, when
  `docs/index.json` changes materially, regenerates a per-module `docs/<module>.md` summary.
- The Action commits regenerated docs back, or opens a PR (prefer PR for review).
- Doc *prose* generation (summaries) may use `cursor-agent --model auto`; the index refresh
  itself stays deterministic.
- Acceptance: pushing a code change updates the relevant `docs/*.md` automatically.

### Phase 3 — RADAR research loop
- Scheduled Action (cron). Reads `docs/index.json`, runs `cursor-agent --model auto` to
  produce findings (stale modules, churn hotspots without tests, dependency risks), writes
  them to `docs/radar/<date>.md`.
- Acceptance: a scheduled run produces a dated findings file with cited file paths.

### Phase 4 — ticket pipeline (human gate)
- RADAR findings → `cursor-agent --model auto` drafts candidate issues (JSON).
- A workflow opens them as GitHub Issues labeled `radar:proposed` (NOT yet actionable).
- Human approves by swapping the label to `radar:approved`. Nothing downstream acts on a
  proposed issue.
- Acceptance: findings become labeled draft issues; only relabeled ones proceed.

### Phase 5 — executor
- Action triggered on `radar:approved` (or `@cursor`-style comment). Installs the CLI,
  auths via `CURSOR_API_KEY`, runs `cursor-agent --force --model composer-2.5` against the
  issue in a fresh branch, runs tests, opens a PR linked to the issue.
- Acceptance: an approved issue yields a PR with passing tests and a minimal diff.

### Phase 6 — hosting
- GitHub Action builds `docs/` and publishes the dashboard to GitHub Pages on push.
- Acceptance: the dashboard is live at the Pages URL and reflects the latest scan.

## GitHub Actions (sketch for Phase 5)

```yaml
name: executor
on:
  issues:
    types: [labeled]
jobs:
  run:
    if: github.event.label.name == 'radar:approved'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: curl https://cursor.com/install -fsSL | bash
      - env:
          CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
        run: |
          git checkout -b "issue-${{ github.event.issue.number }}"
          cursor-agent -p --force --model composer-2.5 \
            "Implement issue #${{ github.event.issue.number }}: ${{ github.event.issue.title }}. Run tests."
      - uses: peter-evans/create-pull-request@v6
        with:
          title: "fix: #${{ github.event.issue.number }}"
          branch: "issue-${{ github.event.issue.number }}"
```

## Known limitations / open questions

- Flat-layout repos emit empty `package_roots`; src/setuptools layouts are detected for import resolution.
- Churn uses full history; very large repos may want a `--since` window for speed.
- Graph caps at 200 nodes (by LOC) to stay readable; large monorepos need clustering/filtering.
- Decide: regenerate docs in-place vs always via PR (PR is safer, more noise).
- Decide: RADAR cadence (daily vs weekly) — affects included-pool consumption.
