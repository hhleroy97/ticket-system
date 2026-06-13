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

The weekly `.github/workflows/radar.yml` job can also produce findings via Auto research;
`radar_report.py` is the deterministic, stdlib-only path for the same markdown shape.
