# RADAR findings

Dated reports live here as `YYYY-MM-DD.md`. Each file lists candidate findings with
**Files:** paths (from `docs/index.json`) and **Rationale:** context for human review.

Generate a report locally after scanning:

```bash
python3 scan.py
python3 radar_report.py              # writes docs/radar/<today-utc>.md
python3 radar_report.py --stdout     # print without writing
```

Parse findings into issue JSON:

```bash
python3 draft_issues.py docs/radar/YYYY-MM-DD.md
```

## Stale high-churn modules

`radar_report.py` compares production Python modules at or above a churn threshold
against non-test importers in `docs/index.json`. When every indexed importer has
fewer commits than the hotspot, the report emits **Stale High-Churn Modules With
Quiet Dependents** so ticket drafting can prompt updates to lagging dependents
(for example `scripts/create_radar_issues.py` after `draft_issues.py` changes).

The weekly `.github/workflows/radar.yml` job can also produce findings via Auto research;
`radar_report.py` is the deterministic, stdlib-only path for the same markdown shape.

## Dependency graph coverage

`check_dependency_graph` in `radar_report.py` reads `stats.edge_count` and the indexed
production Python modules (excluding `tests/`, `test-repos/`, and `test_*.py` paths). It
emits:

- **Dependency Graph Has No Edges** when there are at least two production modules but
  `edge_count` is zero — dependency-risk and stale-dependent analysis cannot trace imports.
- **Dependency Graph Is Sparse** when there are at least three modules but fewer than
  `n - 1` edges — the graph may not connect enough modules for reliable tracing.
- **Dependency Graph Coverage Looks Adequate** otherwise — enough edges exist for basic
  dependency tracing.

`scan.py` builds the underlying `edges` list and `edge_count`; `tests/test_scan.py` asserts
the primary repo index meets the adequacy threshold after each scan.
