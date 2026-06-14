import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FIXTURE = HERE / "tests" / "fixtures" / "index_with_graph.json"
sys.path.insert(0, str(HERE / "scripts"))

from agent_plan import reach_summary_for_files  # noqa: E402


class AgentPlanReachTests(unittest.TestCase):
    def test_reach_summary_empty_paths(self):
        self.assertEqual(reach_summary_for_files([]), [])

    def test_reach_summary_with_fixture_graph(self):
        summary = reach_summary_for_files(
            ["alpha.py"],
            depth=1,
            index_path=FIXTURE,
        )
        self.assertEqual(summary[0]["file"], "alpha.py")
        self.assertIn("neighbors", summary[0])
        labels = {n["label"] for n in summary[0]["neighbors"]}
        self.assertIn("beta.py", labels)


if __name__ == "__main__":
    unittest.main()
