import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from operator_feedback import append_feedback, load_feedback, score_finding  # noqa: E402
from reflect_cycle import already_logged, plan_paths_for_issue, reflect_outcomes  # noqa: E402


class ReflectCycleTests(unittest.TestCase):
    def test_already_logged(self):
        entries = [{"action": "ci_failed", "issue_number": 5}]
        self.assertTrue(already_logged(entries, "ci_failed", 5))
        self.assertFalse(already_logged(entries, "ci_passed", 5))

    def test_reflect_logs_ci_failure(self):
        tmp = tempfile.TemporaryDirectory()
        fb = Path(tmp.name) / "feedback.jsonl"
        index = {
            "pipeline": {
                "tickets": [
                    {"issue_number": 12, "title": "Fix tests", "agent_run": {"files": ["a.py"]}},
                ]
            },
            "workflow_runs": [
                {
                    "id": 1,
                    "name": "test",
                    "branch": "issue-12",
                    "conclusion": "failure",
                }
            ],
        }
        logged = reflect_outcomes(index, feedback_path=fb)
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0]["action"], "ci_failed")
        self.assertTrue(already_logged(load_feedback(fb), "ci_failed", 12))

    def test_reflect_logs_blast_radius_miss(self):
        tmp = tempfile.TemporaryDirectory()
        fb = Path(tmp.name) / "feedback.jsonl"
        run_dir = Path(tmp.name) / "agent-runs" / "issue-7"
        run_dir.mkdir(parents=True)
        (run_dir / "plan.json").write_text(
            json.dumps(
                {
                    "plan": {"files_likely_touched": ["planned.py"]},
                    "reach": [{"file": "planned.py"}],
                }
            ),
            encoding="utf-8",
        )
        index = {
            "pipeline": {
                "tickets": [
                    {
                        "issue_number": 7,
                        "title": "Add feature",
                        "agent_run": {"files": ["planned.py", "extra.py"]},
                    }
                ]
            },
            "workflow_runs": [],
        }
        import reflect_cycle as rc

        old = rc.AGENT_RUNS
        rc.AGENT_RUNS = Path(tmp.name) / "agent-runs"
        try:
            logged = reflect_outcomes(index, feedback_path=fb)
        finally:
            rc.AGENT_RUNS = old
        actions = [entry["action"] for entry in logged]
        self.assertIn("blast_radius_miss", actions)

    def test_plan_paths_for_issue_missing(self):
        self.assertEqual(plan_paths_for_issue(99999), set())


class OutcomeFeedbackTests(unittest.TestCase):
    def test_ci_failed_lowers_score(self):
        tmp = tempfile.TemporaryDirectory()
        fb = Path(tmp.name) / "feedback.jsonl"
        title = "Improve dashboard reach panel"
        append_feedback("ci_failed", title, path=fb, issue_number=1)
        entries = load_feedback(fb)
        self.assertLess(score_finding(title, entries), 0)


if __name__ == "__main__":
    unittest.main()
