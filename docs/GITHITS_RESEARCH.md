# GitHits research — knowledge graph patterns

Research performed with GitHits MCP while designing KG-1…KG-6. Patterns cited below
informed `scripts/provenance_graph.py`, `scripts/reach_query.py`, and dashboard layers.

## RepoGraph — co-change and blast radius

- **Co-change edges:** files edited together in the same commit, filtered by min frequency
  and commit file-count bounds (see `_compute_co_changes` in RepoGraph).
- **Blast radius:** BFS over mixed edge types (imports + co-change + provenance) with depth cap.
- **Applied here:** `CO_CHANGE_MIN_FREQ`, `CO_CHANGE_MIN_FILES` / `MAX_FILES` in
  `provenance_graph.py`; undirected BFS in `reach_query.py` and `agent_plan.reach_summary_for_files`.

## GitCortex — incremental graph maintenance

- Post-commit hooks refresh graph incrementally instead of full rebuilds.
- Branch-aware indexing keeps agent context scoped to active work.
- **Applied here:** full rebuild after each `github_intel.py` run (acceptable at current scale);
  future hook could call `merge_provenance_into_index` on push.

## emerge — D3 force export

- Exports nodes/links JSON suitable for `d3.forceSimulation`.
- **Applied here:** dashboard reuses scan `files`/`edges` for structure layer; provenance
  `co_changed` edges merged when Co-change layer is toggled on.

## Multi-repo federation

- Tag graph nodes with repo slug; query across federated stores.
- **Applied here:** `meta.federation.primary_slug` + `docs_path` in scan output; roadmap for
  `docs/targets/<slug>/` in `KNOWLEDGE_GRAPH_PLAN.md`.

## Agent planning context

- Subgraph extraction around planned files reduces executor prompt noise.
- **Applied here:** `agent_plan.py` writes `reach` array into `plan.json` using graph BFS.
