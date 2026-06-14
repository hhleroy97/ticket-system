import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from provenance_graph import build_provenance_graph, merge_provenance_into_index  # noqa: E402


class ProvenanceGraphTests(unittest.TestCase):
    def test_build_graph_on_fixture_repo(self):
        fixture = HERE / "test-repos" / "srcpkg"
        index = {
            "schema_version": 2,
            "files": [
                {"path": "src/mypkg/core.py", "lang": "Python", "loc": 10},
                {"path": "tests/test_core.py", "lang": "Python", "loc": 5},
            ],
            "edges": [{"source": "tests/test_core.py", "target": "src/mypkg/core.py"}],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, fixture)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("stats", graph)
        kinds = {n["kind"] for n in graph["nodes"]}
        self.assertIn("file", kinds)
        self.assertGreaterEqual(graph["stats"]["node_count"], 2)

    def test_merge_bumps_schema(self):
        index = {
            "schema_version": 2,
            "files": [],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        merge_provenance_into_index(index, HERE)
        self.assertGreaterEqual(index["schema_version"], 3)
        self.assertIn("graph", index)

    def test_co_change_stats_key(self):
        index = {
            "files": [{"path": "scan.py", "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, HERE)
        self.assertIn("co_change_edges", graph["stats"])


if __name__ == "__main__":
    unittest.main()
