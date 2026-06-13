import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FIXTURE = HERE / "test-repos" / "srcpkg"
FIXTURE_DOCS = FIXTURE / "docs"
REPORT = HERE / "radar_report.py"
DRAFT = HERE / "draft_issues.py"

import sys

sys.path.insert(0, str(HERE))
from radar_report import CHURN_THRESHOLD, check_dependency_graph, check_stale_high_churn
from draft_issues import ISSUE_KEYS


class StaleHighChurnTests(unittest.TestCase):
    def test_flags_hotspot_when_indexed_importers_are_quieter(self):
        files = [
            {"path": "hotspot.py", "lang": "Python", "commits": 5, "loc": 10},
            {"path": "consumer.py", "lang": "Python", "commits": 1, "loc": 5},
        ]
        edges = [{"source": "consumer.py", "target": "hotspot.py"}]
        report = check_stale_high_churn(files, edges)
        self.assertIn("Stale High-Churn Modules With Quiet Dependents", report)
        self.assertIn("`hotspot.py`", report)

    def test_skips_when_importer_matches_churn(self):
        churn = max(CHURN_THRESHOLD, 3)
        files = [
            {"path": "hotspot.py", "lang": "Python", "commits": churn, "loc": 10},
            {"path": "consumer.py", "lang": "Python", "commits": churn, "loc": 5},
        ]
        edges = [{"source": "consumer.py", "target": "hotspot.py"}]
        report = check_stale_high_churn(files, edges)
        self.assertIn("No Stale High-Churn Modules Detected", report)
        self.assertNotIn("`hotspot.py`", report)

    def test_ignores_importers_missing_from_index(self):
        files = [{"path": "hotspot.py", "lang": "Python", "commits": 5, "loc": 10}]
        edges = [{"source": "missing.py", "target": "hotspot.py"}]
        report = check_stale_high_churn(files, edges)
        self.assertIn("No Stale High-Churn Modules Detected", report)

    def test_primary_index_no_stale_draft_issues_hotspot(self):
        index = json.loads((HERE / "docs" / "index.json").read_text())
        report = check_stale_high_churn(index["files"], index["edges"])
        self.assertIn("No Stale High-Churn Modules Detected", report)
        self.assertNotIn("`draft_issues.py`", report)


class DependencyGraphTests(unittest.TestCase):
    def _py_files(self, paths):
        return [{"path": path, "lang": "Python", "commits": 1, "loc": 10} for path in paths]

    def test_flags_no_edges_when_modules_exist(self):
        files = self._py_files(["alpha.py", "beta.py"])
        report = check_dependency_graph(files, [], {"edge_count": 0})
        self.assertIn("Dependency Graph Has No Edges", report)
        self.assertIn("`scan.py`", report)

    def test_flags_sparse_when_below_minimum_edges(self):
        files = self._py_files(["a.py", "b.py", "c.py", "d.py"])
        report = check_dependency_graph(files, [], {"edge_count": 2})
        self.assertIn("Dependency Graph Is Sparse", report)
        self.assertIn("4 production Python modules but only 2 import edge", report)

    def test_reports_adequate_when_threshold_met(self):
        files = self._py_files(["a.py", "b.py", "c.py", "d.py"])
        report = check_dependency_graph(files, [], {"edge_count": 3})
        self.assertIn("Dependency Graph Coverage Looks Adequate", report)
        self.assertIn("3 import edge(s) across 4 production Python module(s)", report)

    def test_two_modules_with_one_edge_is_adequate(self):
        files = self._py_files(["a.py", "b.py"])
        report = check_dependency_graph(files, [], {"edge_count": 1})
        self.assertIn("Dependency Graph Coverage Looks Adequate", report)
        self.assertNotIn("Sparse", report)

    def test_primary_index_reports_adequate_coverage(self):
        index = json.loads((HERE / "docs" / "index.json").read_text())
        report = check_dependency_graph(index["files"], index["edges"], index["stats"])
        self.assertIn("Dependency Graph Coverage Looks Adequate", report)
        self.assertIn("`scan.py`", report)


class RadarReportTests(unittest.TestCase):
    def run_scan(self, target):
        env = {**__import__("os").environ, "TARGET_REPO": str(target)}
        proc = subprocess.run(
            ["python3", str(HERE / "scan.py")],
            capture_output=True,
            text=True,
            cwd=HERE,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    def generate_report(self, target, date="2026-06-13", stdout=True):
        env = {**__import__("os").environ, "TARGET_REPO": str(target)}
        args = ["python3", str(REPORT), "--date", date]
        if stdout:
            args.append("--stdout")
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=HERE,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        return proc.stdout

    def test_report_has_required_sections(self):
        self.run_scan(FIXTURE)
        report = self.generate_report(FIXTURE)
        self.assertIn("# RADAR 2026-06-13", report)
        self.assertIn("**Files:**", report)
        self.assertIn("**Rationale:**", report)
        self.assertGreaterEqual(report.count("## "), 2)

    def test_report_parsable_by_draft_issues(self):
        self.run_scan(FIXTURE)
        report = self.generate_report(FIXTURE)
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(report)
            path = fh.name
        proc = subprocess.run(
            ["python3", str(DRAFT), path],
            capture_output=True,
            text=True,
            check=True,
        )
        issues = json.loads(proc.stdout)
        self.assertGreaterEqual(len(issues), 2)
        for item in issues:
            self.assertEqual(set(item), set(ISSUE_KEYS))
            self.assertIn("title", item)
            self.assertIn("body", item)
            self.assertIn("rationale", item)
            self.assertIn("files", item)

    def test_fixture_flags_untested_production_module(self):
        self.run_scan(FIXTURE)
        report = self.generate_report(FIXTURE)
        self.assertIn("Production Python Modules Lack Test Import Edges", report)
        self.assertIn("src/mypkg/__init__.py", report)
        self.assertNotIn("src/mypkg/core.py", report.split("Lack Test Import Edges", 1)[-1])

    def test_writes_dated_file(self):
        self.run_scan(FIXTURE)
        env = {**__import__("os").environ, "TARGET_REPO": str(FIXTURE)}
        out = FIXTURE_DOCS / "radar" / "2099-01-01.md"
        out.unlink(missing_ok=True)
        proc = subprocess.run(
            ["python3", str(REPORT), "--date", "2099-01-01"],
            capture_output=True,
            text=True,
            cwd=HERE,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertTrue(out.is_file())
        text = out.read_text()
        self.assertIn("# RADAR 2099-01-01", text)
        out.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
