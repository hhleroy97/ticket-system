import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from graph_lib import (  # noqa: E402
    co_change_neighbors,
    file_node_id,
    load_provenance,
    reach_query,
)


class GraphLibTests(unittest.TestCase):
    def test_fixture_reach(self):
        fixture = HERE / "tests" / "fixtures" / "index_with_graph.json"
        index = json.loads(fixture.read_text())
        result = reach_query("alpha.py", depth=1, index=index)
        self.assertFalse(result.get("missing"))
        labels = {item["label"] for item in result["reachable"]}
        self.assertIn("beta.py", labels)

    def test_co_change_neighbors(self):
        fixture = HERE / "tests" / "fixtures" / "index_with_graph.json"
        index = json.loads(fixture.read_text())
        _, edges, _ = load_provenance(index)
        neighbors = co_change_neighbors("alpha.py", edges, min_weight=1)
        self.assertEqual(neighbors, [])

    def test_file_node_id(self):
        self.assertEqual(file_node_id("scan.py"), "file:scan.py")


if __name__ == "__main__":
    unittest.main()
