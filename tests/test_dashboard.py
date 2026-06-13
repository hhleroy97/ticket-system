import json
import re
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCAN = HERE / "scan.py"
FIXTURE = HERE / "test-repos" / "srcpkg"
FIXTURE_DOCS = FIXTURE / "docs"
TEMPLATE = HERE / "templates" / "dashboard.html.tmpl"

import sys

sys.path.insert(0, str(HERE))
from scan import DATA_PLACEHOLDER, render_dashboard


def extract_embedded_data(html):
    match = re.search(r"const DATA = (.+);\n", html)
    if not match:
        raise AssertionError("dashboard HTML missing embedded DATA object")
    return json.loads(match.group(1))


class RenderDashboardTests(unittest.TestCase):
    def test_template_placeholder_replaced(self):
        index = {
            "schema_version": 1,
            "repo": {"name": "fixture-repo"},
            "stats": {"file_count": 3, "total_loc": 42, "edge_count": 1, "contributor_count": 2},
            "languages": [{"name": "Python", "files": 2, "loc": 40}],
            "files": [{"path": "src/mypkg/core.py", "lang": "Python", "loc": 20, "commits": 1}],
            "edges": [{"source": "tests/test_core.py", "target": "src/mypkg/core.py"}],
        }
        html = render_dashboard(index)
        self.assertNotIn(DATA_PLACEHOLDER, html)
        data = extract_embedded_data(html)
        self.assertEqual(data["repo"]["name"], "fixture-repo")
        self.assertEqual(data["stats"]["file_count"], 3)

    def test_rendered_html_preserves_shell(self):
        index = {
            "repo": {"name": "x"},
            "stats": {},
            "languages": [],
            "files": [],
            "edges": [],
        }
        html = render_dashboard(index)
        shell = TEMPLATE.read_text()
        self.assertIn('id="repoName"', html)
        self.assertIn('id="graph"', html)
        self.assertIn('id="langs"', html)
        self.assertIn('id="hot"', html)
        self.assertIn("const DATA = ", html)
        self.assertIn(shell.split("const DATA = ")[0], html)
        self.assertIn(shell.split(";\nconst fmt")[1], html)


class ScanDashboardTests(unittest.TestCase):
    def run_scan(self, target):
        env = {**__import__("os").environ, "TARGET_REPO": str(target)}
        proc = subprocess.run(
            ["python3", str(SCAN)],
            capture_output=True,
            text=True,
            cwd=HERE,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    def test_scan_writes_dashboard_matching_index(self):
        self.run_scan(FIXTURE)
        index = json.loads((FIXTURE_DOCS / "index.json").read_text())
        html = (FIXTURE_DOCS / "dashboard.html").read_text()
        data = extract_embedded_data(html)
        self.assertEqual(data["repo"]["name"], index["repo"]["name"])
        self.assertEqual(data["stats"], index["stats"])
        self.assertEqual(data["files"], index["files"])
        self.assertEqual(data["edges"], index["edges"])


if __name__ == "__main__":
    unittest.main()
