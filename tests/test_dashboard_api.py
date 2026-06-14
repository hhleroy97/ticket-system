import json
import sys
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from dashboard_api import parse_api_path, approve_issue  # noqa: E402


class ParseApiPathTests(unittest.TestCase):
    def test_workflows(self):
        self.assertEqual(parse_api_path("/api/workflows", "GET"), ("workflows", None))

    def test_workflow_run(self):
        self.assertEqual(parse_api_path("/api/workflows/12345", "GET"), ("workflow_run", 12345))

    def test_issues_list(self):
        self.assertEqual(parse_api_path("/api/issues", "GET"), ("issues", None))

    def test_approve(self):
        self.assertEqual(parse_api_path("/api/issues/21/approve", "POST"), ("approve", 21))

    def test_dismiss(self):
        self.assertEqual(parse_api_path("/api/issues/21/dismiss", "POST"), ("dismiss", 21))

    def test_request(self):
        self.assertEqual(parse_api_path("/api/request", "POST"), ("request", None))

    def test_reach(self):
        self.assertEqual(parse_api_path("/api/reach?from=scan.py", "GET"), ("reach", None))

    def test_feedback(self):
        self.assertEqual(parse_api_path("/api/feedback", "GET"), ("feedback", None))


class ReachQueryTests(unittest.TestCase):
    def test_query_reach_uses_index(self):
        from dashboard_api import query_reach  # noqa: E402

        if not (HERE / "docs" / "index.json").is_file():
            self.skipTest("index.json missing")
        result = query_reach("scan.py", depth=1)
        self.assertIn("reachable", result)


class ApproveIssueTests(unittest.TestCase):
    @patch("dashboard_api.append_feedback")
    @patch("dashboard_api.subprocess.run")
    def test_adds_labels(self, mock_run, _mock_feedback):
        mock_run.side_effect = [
            mock.Mock(
                returncode=0,
                stdout=json.dumps({"title": "Fix thing", "labels": []}),
            ),
            mock.Mock(returncode=0, stdout="", stderr=""),
        ]
        result, err = approve_issue("owner/repo", 21, auto_merge=True)
        self.assertIsNone(err)
        self.assertEqual(result["labels_added"], ["radar:approved", "radar:auto-merge"])
        self.assertEqual(result["labels_removed"], ["radar:proposed"])
        edit_cmd = mock_run.call_args_list[1][0][0]
        self.assertIn("edit", edit_cmd)
        self.assertIn("--remove-label", edit_cmd)


if __name__ == "__main__":
    unittest.main()
