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
- **Roadmap:** `docs/KNOWLEDGE_GRAPH_PLAN.md` — git provenance graph, PR/commit/CI navigation, multi-repo

## Git provenance knowledge graphs (research)

| Project | URL | Relevant patterns |
| --- | --- | --- |
| **RepoGraph** | https://github.com/FalkorDB/RepoGraph | commit→file→module graph, co-change coupling, blast radius, D3 force UI |
| **GitCortex** | https://github.com/bharath03-a/gitcortex | incremental commit indexing, branch-aware graph, MCP queries, `gcx viz` |
| **Noumenon** | https://github.com/leifericf/noumenon | staged pipeline: import → enrich → analyze; commits/authors as entities |
| **git-mind** | https://github.com/flyingrobots/git-mind | Git-native semantic graph; issues/tasks/commits with provenance replay |
| **git-warp** | https://github.com/git-stunts/git-warp | Causal provenance substrate; worldlines for versioned graph state |

### Planned adoption (see KNOWLEDGE_GRAPH_PLAN.md)

- **KG-1:** commit/PR nodes + `modifies` / `contains` edges (deterministic)
- **KG-2:** workflow run/step nodes linked to pipeline tickets
- **KG-3:** layered force graph (structure + provenance + CI)
- **KG-5:** `TARGET_REPO` switch for analyzing other repos with same contract
