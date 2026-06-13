#!/usr/bin/env python3
"""
Deterministic RADAR finding report from docs/index.json (no LLM).

Reads scan output and writes dated markdown under docs/radar/ with sections
parseable by draft_issues.py (**Files:** / **Rationale:** per finding).
"""

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE_ROOT = HERE / "test-repos"
CHURN_THRESHOLD = 2
DATED_RADAR = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def resolve_docs(repo):
    repo = repo.resolve()
    if repo == HERE.resolve():
        return HERE / "docs"
    try:
        repo.relative_to(FIXTURE_ROOT)
        return repo / "docs"
    except ValueError:
        return HERE / "docs"


def docs_for_report():
    target = os.environ.get("TARGET_REPO")
    if target:
        return resolve_docs(Path(target).expanduser().resolve())
    return HERE / "docs"


def is_test_path(path):
    name = Path(path).name
    return (
        path.startswith("tests/")
        or path.startswith("test-repos/")
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def production_python(files):
    return [
        f
        for f in files
        if f.get("lang") == "Python"
        and f["path"].endswith(".py")
        and not is_test_path(f["path"])
    ]


def build_graph(edges):
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for edge in edges:
        incoming[edge["target"]].append(edge["source"])
        outgoing[edge["source"]].append(edge["target"])
    return incoming, outgoing


def format_files(paths):
    return ", ".join(f"`{path}`" for path in paths)


def render_finding(title, files, rationale):
    return "\n".join(
        [
            f"## {title}",
            f"**Files:** {format_files(files)}",
            f"**Rationale:** {rationale}",
            "",
        ]
    )


def check_stale_high_churn(files, edges):
    incoming, _ = build_graph(edges)
    hotspots = [f for f in production_python(files) if f["commits"] >= CHURN_THRESHOLD]
    stale = []
    for meta in hotspots:
        importers = [src for src in incoming.get(meta["path"], []) if not is_test_path(src)]
        if not importers:
            continue
        if all(files_by_path(files)[src]["commits"] < meta["commits"] for src in importers if src in files_by_path(files)):
            stale.append(meta["path"])
    if stale:
        return render_finding(
            "Stale High-Churn Modules With Quiet Dependents",
            sorted(set(stale)) + ["docs/index.json"],
            "These modules have elevated commit counts while indexed importers "
            "show fewer commits, suggesting dependent code may not have kept pace "
            "with hotspot changes.",
        )
    return render_finding(
        "No Stale High-Churn Modules Detected",
        ["docs/index.json"],
        "No indexed production Python module both exceeds the churn threshold and "
        "has importers with lower commit counts.",
    )


def files_by_path(files):
    return {f["path"]: f for f in files}


def check_dependency_graph(files, edges, stats):
    py_modules = production_python(files)
    edge_count = stats.get("edge_count", len(edges))
    if len(py_modules) >= 2 and edge_count == 0:
        paths = sorted(f["path"] for f in py_modules)[:8]
        if len(py_modules) > len(paths):
            paths.append("docs/index.json")
        else:
            paths = sorted(set(paths + ["docs/index.json", "scan.py"]))
        return render_finding(
            "Dependency Graph Has No Edges",
            paths,
            "`docs/index.json` reports `edge_count: 0` and an empty or missing "
            "`edges` list, so dependency-risk and dependent-recency analysis cannot "
            "trace relationships among indexed Python modules.",
        )
    if len(py_modules) >= 3 and edge_count < len(py_modules) - 1:
        paths = sorted({*(f["path"] for f in py_modules[:6]), "docs/index.json", "scan.py"})
        return render_finding(
            "Dependency Graph Is Sparse",
            paths,
            f"The index tracks {len(py_modules)} production Python modules but only "
            f"{edge_count} import edge(s), limiting confidence in dependency-risk "
            "and stale-dependent analysis.",
        )
    return render_finding(
        "Dependency Graph Coverage Looks Adequate",
        ["docs/index.json", "scan.py"],
        f"The index reports {edge_count} import edge(s) across {len(py_modules)} "
        "production Python module(s), enough for basic dependency tracing.",
    )


def check_untested_modules(files, edges):
    incoming, _ = build_graph(edges)
    tested = {
        target
        for target, sources in incoming.items()
        if any(is_test_path(src) for src in sources)
    }
    untested = sorted(
        f["path"]
        for f in production_python(files)
        if f["path"] not in tested and f["loc"] > 0
    )
    if untested:
        test_files = sorted(f["path"] for f in files if is_test_path(f["path"]) and f.get("lang") == "Python")
        return render_finding(
            "Production Python Modules Lack Test Import Edges",
            untested + test_files[:4] + ["docs/index.json"],
            "Indexed tests do not import these production modules, so churn and "
            "dependency signals may not reflect test coverage gaps.",
        )
    return render_finding(
        "Production Python Modules Have Test Import Edges",
        ["docs/index.json"],
        "Every indexed production Python module is imported by at least one test file "
        "according to the dependency graph.",
    )


def check_dashboard_tests(files, edges):
    dash_paths = sorted(
        f["path"]
        for f in files
        if "dashboard" in f["path"].lower() and f["path"].endswith((".html", ".tmpl", ".py"))
    )
    if not dash_paths:
        return ""
    referenced = {edge["target"] for edge in edges} | {edge["source"] for edge in edges}
    if any(path in referenced for path in dash_paths):
        return ""
    test_paths = sorted(f["path"] for f in files if is_test_path(f["path"]))
    return render_finding(
        "Dashboard Generation Lacks Focused Tests",
        dash_paths + test_paths[:3],
        "The dashboard template and generated HTML are indexed, but no test module "
        "imports them or asserts rendered output, leaving dashboard drift undetected.",
    )


def check_radar_pipeline(files):
    paths = {f["path"] for f in files}
    radar_paths = sorted(p for p in paths if p.startswith("docs/radar/"))
    dated = [p for p in radar_paths if DATED_RADAR.match(Path(p).name)]
    tool_paths = sorted(p for p in ("radar_report.py", "draft_issues.py") if p in paths)
    test_paths = sorted(p for p in paths if p.startswith("tests/test_radar"))
    if not tool_paths:
        return ""
    if not dated:
        return render_finding(
            "RADAR Findings Directory Has No Dated Reports",
            radar_paths + tool_paths,
            "`docs/radar/` only contains placeholder documentation. Run "
            "`python3 radar_report.py` after `scan.py` to emit a dated findings file "
            "for human review and ticket drafting.",
        )
    if "radar_report.py" in paths and not test_paths:
        return render_finding(
            "RADAR Report Generator Lacks Focused Tests",
            tool_paths + dated[:2] + ["docs/radar/README.md"],
            "Deterministic RADAR tooling is indexed but no dedicated test module "
            "asserts report shape or draft_issues compatibility.",
        )
    return ""


def generate_findings(index):
    files = index.get("files", [])
    edges = index.get("edges", [])
    stats = index.get("stats", {})
    sections = [
        check_stale_high_churn(files, edges),
        check_dependency_graph(files, edges, stats),
        check_untested_modules(files, edges),
        check_dashboard_tests(files, edges),
        check_radar_pipeline(files),
    ]
    return [section for section in sections if section]


def render_report(date_str, index):
    lines = [f"# RADAR {date_str}", ""]
    lines.extend(generate_findings(index))
    return "\n".join(lines).rstrip() + "\n"


def default_date():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        help="Report date (YYYY-MM-DD). Defaults to today UTC.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print report to stdout instead of writing docs/radar/<date>.md",
    )
    args = parser.parse_args()

    docs = docs_for_report()
    index_path = docs / "index.json"
    if not index_path.is_file():
        raise SystemExit(f"missing {index_path}; run scan.py first")

    index = json.loads(index_path.read_text())
    date_str = args.date or default_date()
    report = render_report(date_str, index)

    if args.stdout:
        print(report, end="")
        return

    out_dir = docs / "radar"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.md"
    out_path.write_text(report)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
