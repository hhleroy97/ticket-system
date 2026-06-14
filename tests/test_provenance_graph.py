import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from provenance_graph import build_provenance_graph, merge_provenance_into_index, node_id  # noqa: E402
from graph_lib import authors_for_file, load_provenance  # noqa: E402


def make_author_git_fixture():
    """Minimal git repo with one commit so author edges are CI-independent."""
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    rel_path = "src/sample.py"
    (repo / "src").mkdir(parents=True)
    (repo / rel_path).write_text("x = 1\n", encoding="utf-8")
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "author@example.com"],
        ["git", "config", "user.name", "Fixture Author"],
        ["git", "add", "."],
        ["git", "commit", "-m", "add sample"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True, text=True)
    return tmp, repo, rel_path


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
        tmp, repo, path = make_author_git_fixture()
        self.addCleanup(tmp.cleanup)
        index = {
            "files": [{"path": path, "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, repo)
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
        tmp, repo, path = make_author_git_fixture()
        self.addCleanup(tmp.cleanup)
        index = {
            "files": [{"path": path, "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, repo)
        self.assertIn("author_nodes", graph["stats"])
        self.assertIn("authored_edges", graph["stats"])
        self.assertGreaterEqual(graph["stats"]["author_nodes"], 1)
        self.assertGreaterEqual(graph["stats"]["authored_edges"], 1)

    def test_authors_for_file_helper(self):
        tmp, repo, path = make_author_git_fixture()
        self.addCleanup(tmp.cleanup)
        index = {
            "files": [{"path": path, "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [],
            "issues": [],
            "workflow_runs": [],
        }
        graph = build_provenance_graph(index, repo)
        index["graph"] = graph
        _, edges, node_by_id = load_provenance(index)
        authors = authors_for_file(path, edges, node_by_id)
        self.assertGreater(len(authors), 0)
        self.assertGreaterEqual(authors[0][1], 1)

    def test_workflow_step_nodes_and_edges(self):
        index = {
            "files": [{"path": "scan.py", "lang": "Python", "loc": 1}],
            "edges": [],
            "pull_requests": [],
            "open_pull_requests": [
                {
                    "number": 47,
                    "head_ref": "issue-46",
                    "issue_numbers": [46],
                    "commits": [{"sha": "abc1234", "files": ["scan.py"]}],
                }
            ],
            "issues": [{"number": 46, "title": "test issue"}],
            "workflow_runs": [
                {
                    "id": 99001,
                    "name": "test",
                    "branch": "issue-46",
                    "status": "completed",
                    "conclusion": "failure",
                    "jobs": [
                        {
                            "name": "test",
                            "steps": [
                                {
                                    "name": "Run tests",
                                    "number": 3,
                                    "status": "completed",
                                    "conclusion": "failure",
                                }
                            ],
                        }
                    ],
                }
            ],
            "pipeline": {
                "tickets": [
                    {
                        "issue_number": 46,
                        "agent_run": {"files": ["scan.py"]},
                    }
                ]
            },
        }
        graph = build_provenance_graph(index, HERE)
        steps = [n for n in graph["nodes"] if n["kind"] == "workflow_step"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["name"], "Run tests")
        self.assertIn("workflow_step_nodes", graph["stats"])
        self.assertEqual(graph["stats"]["workflow_step_nodes"], 1)

        has_step = [e for e in graph["edges"] if e["type"] == "has_step"]
        self.assertEqual(len(has_step), 1)
        covers = [e for e in graph["edges"] if e["type"] == "covers"]
        self.assertGreaterEqual(len(covers), 1)
        self.assertEqual(covers[0]["target"], node_id("file", "scan.py"))
        failed = [e for e in graph["edges"] if e["type"] == "failed_at"]
        self.assertEqual(len(failed), 1)


if __name__ == "__main__":
    unittest.main()
