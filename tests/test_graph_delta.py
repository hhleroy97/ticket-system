import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DELTA = HERE / "scripts" / "graph_delta.py"


class GraphDeltaTests(unittest.TestCase):
    def test_cli_skip_without_graph(self):
        fixture = HERE / "tests" / "fixtures" / "index_with_prs.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(DELTA),
                "--base",
                "main",
                "--head",
                "HEAD",
                "--index",
                str(fixture),
            ],
            capture_output=True,
            text=True,
            cwd=HERE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(data.get("skipped"))


if __name__ == "__main__":
    unittest.main()
