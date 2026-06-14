import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from agent_plan import reach_summary_for_files  # noqa: E402


class AgentPlanReachTests(unittest.TestCase):
    def test_reach_summary_empty_paths(self):
        self.assertEqual(reach_summary_for_files([]), [])

    def test_reach_summary_with_graph(self):
        index_path = HERE / "docs" / "index.json"
        if not index_path.is_file():
            self.skipTest("docs/index.json missing")
        index = json.loads(index_path.read_text())
        if not index.get("graph"):
            self.skipTest("graph not built yet")
        files = [n["path"] for n in index["graph"]["nodes"] if n.get("kind") == "file"][:1]
        if not files:
            self.skipTest("no file nodes")
        summary = reach_summary_for_files(files, depth=1)
        self.assertEqual(summary[0]["file"], files[0])
        self.assertIn("neighbors", summary[0])


if __name__ == "__main__":
    unittest.main()
