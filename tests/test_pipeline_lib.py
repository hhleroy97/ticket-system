import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from pipeline_lib import (  # noqa: E402
    PIPELINE_STAGES,
    build_pipeline,
    infer_stage,
    index_open_prs_by_issue,
    index_runs_by_branch,
)


class InferStageTests(unittest.TestCase):
    def test_proposed_label(self):
        issue = {"number": 1, "labels": ["radar:proposed"]}
        stage, label = infer_stage(issue, {}, {}, set())
        self.assertEqual(stage, "proposed")
        self.assertEqual(label, "Proposed")

    def test_approved_waiting(self):
        issue = {"number": 2, "labels": ["radar:approved"]}
        stage, _label = infer_stage(issue, {}, {}, set())
        self.assertEqual(stage, "approved")

    def test_implementing_when_executor_running(self):
        issue = {"number": 3, "labels": ["radar:approved"]}
        runs = index_runs_by_branch(
            [
                {
                    "branch": "issue-3",
                    "status": "in_progress",
                    "name": "executor",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        )
        stage, label = infer_stage(issue, {}, runs, set())
        self.assertEqual(stage, "implementing")
        self.assertEqual(label, "Agent working")

    def test_pr_open_with_open_pr(self):
        issue = {"number": 4, "labels": ["radar:approved"], "linked_prs": [10]}
        open_prs = index_open_prs_by_issue(
            [{"number": 10, "head_ref": "issue-4", "issue_numbers": [4]}]
        )
        stage, _label = infer_stage(issue, open_prs, {}, set())
        self.assertEqual(stage, "pr_open")

    def test_ci_when_test_running(self):
        issue = {"number": 5, "labels": ["radar:approved"]}
        open_prs = index_open_prs_by_issue(
            [{"number": 11, "head_ref": "issue-5", "issue_numbers": [5]}]
        )
        stage, label = infer_stage(issue, open_prs, {}, {"issue-5"})
        self.assertEqual(stage, "ci")
        self.assertEqual(label, "CI running")


class BuildPipelineTests(unittest.TestCase):
    def test_builds_ticket_entries(self):
        issues = [
            {"number": 7, "title": "Fix thing", "labels": ["radar:proposed"], "linked_prs": []},
            {"number": 8, "title": "Ship it", "labels": ["radar:approved"], "linked_prs": []},
        ]
        pipeline = build_pipeline(issues, [], [], [], HERE)
        self.assertEqual(len(pipeline["stages"]), len(PIPELINE_STAGES))
        self.assertEqual(len(pipeline["tickets"]), 2)
        self.assertEqual(pipeline["tickets"][0]["issue_number"], 7)
        self.assertIn("stage", pipeline["tickets"][0])


class FinalizeAgentRunTests(unittest.TestCase):
    def test_capture_writes_run_json(self):
        import finalize_agent_run

        with patch("finalize_agent_run.branch_commits", return_value=[{"sha": "abc1234", "message": "feat: x", "files": ["a.py"]}]), \
             patch("finalize_agent_run.branch_files", return_value=["a.py"]), \
             patch("finalize_agent_run.diff_stat", return_value="1 file changed"), \
             patch.object(finalize_agent_run, "HERE", HERE):
            run_dir = HERE / "docs" / "agent-runs" / "issue-9999"
            run_path = run_dir / "run.json"
            if run_path.is_file():
                run_path.unlink()
            payload = finalize_agent_run.capture(9999, "main", snapshot=True)
            self.assertEqual(payload["issue_number"], 9999)
            self.assertEqual(payload["commit_count"], 1)
            self.assertTrue(run_path.is_file())
            run_path.unlink()
            if run_dir.is_dir() and not any(run_dir.iterdir()):
                run_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
