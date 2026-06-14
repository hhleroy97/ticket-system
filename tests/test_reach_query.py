import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REACH = HERE / "scripts" / "reach_query.py"
FIXTURE = HERE / "tests" / "fixtures" / "index_with_graph.json"
MISSING = HERE / "tests" / "fixtures" / "missing-index.json"


class ReachQueryTests(unittest.TestCase):
    def run_reach(self, *args):
        return subprocess.run(
            [sys.executable, str(REACH), *args],
            capture_output=True,
            text=True,
            cwd=HERE,
        )

    def test_cli_errors_when_index_missing(self):
        proc = self.run_reach("--from", "alpha.py", "--index", str(MISSING))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("error: missing", proc.stderr)

    def test_cli_queries_fixture_graph(self):
        proc = self.run_reach(
            "--from", "alpha.py",
            "--index", str(FIXTURE),
            "--depth", "1",
            "--undirected",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["start"], "file:alpha.py")
        self.assertIn("reachable", data)
        labels = {item["label"] for item in data["reachable"]}
        self.assertIn("beta.py", labels)

    def test_resolve_file_path_from_fixture(self):
        proc = self.run_reach(
            "--from", "beta.py",
            "--index", str(FIXTURE),
            "--depth", "1",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["depth"], 1)


if __name__ == "__main__":
    unittest.main()
