# Knowledge graph roadmap (KG-1 … KG-6)

Provenance and structure layers over `docs/index.json`. Built deterministically by
`scripts/provenance_graph.py` after `scan.py` + `scripts/github_intel.py`.

| Phase | Deliverable | Status |
|-------|-------------|--------|
| KG-1 | Commit / PR / issue / file nodes; `modifies`, `contains`, `co_changed` | Done |
| KG-2 | Workflow run nodes; `runs_for`, `tests` edges to issues/PRs | Done |
| KG-3 | Dashboard layer toggles (structure / co-change / provenance panel) | Done |
| KG-4 | `scripts/reach_query.py` BFS blast-radius CLI | Done |
| KG-5 | `meta.federation` slug + per-target docs path (multi-repo prep) | Done |
| KG-6 | `reach` subgraph in `docs/agent-runs/issue-*/plan.json` | Done |

## Run

```bash
TARGET_REPO=/home/hartley/projects/personal/ticket-sys python3 scan.py
python3 scripts/github_intel.py
python3 scripts/reach_query.py --from scan.py --depth 2
open docs/dashboard.html
```

## Schema

`schema_version` bumps to **3** when `graph` is present:

```json
{
  "graph": {
    "nodes": [{"id": "file:scan.py", "kind": "file", "path": "scan.py"}],
    "edges": [{"source": "commit:abc1234", "target": "file:scan.py", "type": "modifies"}],
    "stats": {"node_count": 0, "edge_count": 0},
    "built_at": "…"
  }
}
```

SQLite mirrors: `graph_nodes`, `graph_edges` in `docs/index.db`.

## Multi-repo (KG-5 next steps)

- Store secondary targets under `docs/targets/<slug>/index.json`
- Merge graphs with prefixed node ids (`ticket-sys:file:scan.py`)
- Dashboard repo switcher reads `meta.federation`

## References

See `docs/GITHITS_RESEARCH.md` for GitHits-sourced patterns (RepoGraph co-change,
blast radius, GitCortex incremental hooks, emerge D3 export).
