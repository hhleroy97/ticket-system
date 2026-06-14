import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REACH = HERE / "scripts" / "reach_query.py"
INDEX = HERE / "docs" / "index.json"


class ReachQueryTests(unittest.TestCase):
    def test_cli_requires_index(self):
        proc = subprocess.run(
            [sys.executable, str(REACH), "--from", "scan.py"],
            capture_output=True,
            text=True,
            cwd=HERE,
        )
        if INDEX.is_file():
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertIn("reachable", data)
            self.assertEqual(data["start"], "file:scan.py")
        else:
            self.assertNotEqual(proc.returncode, 0)

    def test_resolve_file_path(self):
        if not INDEX.is_file():
            self.skipTest("docs/index.json missing")
        index = json.loads(INDEX.read_text())
        graph = index.get("graph") or {}
        file_nodes = [n for n in graph.get("nodes", []) if n.get("kind") == "file"]
        if not file_nodes:
            self.skipTest("graph has no file nodes")
        path = file_nodes[0]["path"]
        proc = subprocess.run(
            [sys.executable, str(REACH), "--from", path, "--depth", "1"],
            capture_output=True,
            text=True,
            cwd=HERE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["depth"], 1)


if __name__ == "__main__":
    unittest.main()
