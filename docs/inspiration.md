# Inspiration — similar tools and patterns

Research compiled for repo-intel roadmap decisions. GitHits auth was unavailable during
initial research; sources are public READMEs and project docs (June 2026).

## Codebase intelligence & dependency graphs

| Project | URL | Relevant patterns |
| --- | --- | --- |
| **emerge** | https://github.com/glato/emerge | Force-directed graphs, churn metrics, multi-language scan → standalone HTML export |
| **CodeMap** | https://github.com/polprog-tech/CodeMap | Hotspots = churn × coupling, git ownership, self-contained HTML, pluggable extractors |
| **CodeBoarding** | https://github.com/codeboarding/codeboarding | Architecture diagrams + agent-facing docs in `.codeboarding/`, CI Action, incremental updates |
| **arkit** | https://github.com/dyatko/arkit | Committable architecture diagrams, CI sync, component grouping |

### What we adopted

- **Self-contained HTML dashboard** with inlined JSON (like emerge/CodeMap)
- **Churn-colored nodes** and import edges (emerge-style exploration)
- **Hotspot findings** in deterministic RADAR (CodeMap-style signals)
- **Agent-readable artifacts** under `docs/agent-runs/` (CodeBoarding-style trace dirs)

### What we deferred

- 3D graphs (Orbis) — 2D D3 is enough for now
- LLM-generated architecture prose on every scan — kept scan deterministic; agents only in executor/RADAR optional paths

## Ticket → agent → PR pipelines

| Pattern | Notes |
| --- | --- |
| **GitHub Issues as queue** | Labels as state machine (`radar:proposed` → `radar:approved`) |
| **Branch per issue** | `issue-<N>` branches, logical commits, `Closes #N` |
| **Human gate** | No executor without `radar:approved` |
| **Auto-merge low-risk** | `auto-merge.yml` + `radar:auto-merge` label after tests |
| **Issue comments for progress** | Common in Dependabot/Renovate-style bots; we post throttled executor snapshots |

## CI/CD conventions

- **PRs for maintainer changes** — `test.yml` on every branch (see AGENTS.md)
- **Bot direct push exception** — `push_to_main.sh` for scheduled scan/RADAR only
- **Worktrees for parallel features** — local `git worktree add ../ticket-sys-wt/<name> -b feat/...`

## Further reading

- GitHub dependency graph (manifest-level, not import AST): repo **Insights → Dependency graph**
- HANDOFF.md build plan vs current implementation gap analysis: see `docs/RUNBOOK.md`
