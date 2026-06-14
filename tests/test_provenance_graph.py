import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from provenance_graph import build_provenance_graph, merge_provenance_into_index, node_id  # noqa: E402
from graph_lib import authors_for_file, load_provenance  # noqa: E402


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

    def test_author_nodes_and_authored_edges(self):
        path = "scripts/provenance_graph.py"
        index = {
            "files": [{"path": path, "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, HERE)
        author_nodes = [n for n in graph["nodes"] if n["kind"] == "author"]
        self.assertGreater(len(author_nodes), 0)
        self.assertTrue(all(n.get("email") or n.get("name") for n in author_nodes))

        authored = [e for e in graph["edges"] if e["type"] == "authored"]
        self.assertGreater(len(authored), 0)
        fid = node_id("file", path)
        file_authored = [e for e in authored if e["target"] == fid]
        self.assertGreater(len(file_authored), 0)
        self.assertGreaterEqual(file_authored[0].get("weight", 0), 1)

    def test_author_stats_keys(self):
        index = {
            "files": [{"path": "scan.py", "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, HERE)
        self.assertIn("author_nodes", graph["stats"])
        self.assertIn("authored_edges", graph["stats"])
        self.assertGreaterEqual(graph["stats"]["author_nodes"], 1)
        self.assertGreaterEqual(graph["stats"]["authored_edges"], 1)

    def test_authors_for_file_helper(self):
        path = "scripts/provenance_graph.py"
        index = {
            "files": [{"path": path, "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, HERE)
        index["graph"] = graph
        _, edges, node_by_id = load_provenance(index)
        authors = authors_for_file(path, edges, node_by_id)
        self.assertGreater(len(authors), 0)
        self.assertGreaterEqual(authors[0][1], 1)


if __name__ == "__main__":
    unittest.main()
