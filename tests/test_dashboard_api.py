import json
import sys
import unittest
from pathlib import Path
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


    def test_reach(self):
        self.assertEqual(parse_api_path("/api/reach?from=scan.py", "GET"), ("reach", None))


class ReachQueryTests(unittest.TestCase):
    def test_query_reach_uses_index(self):
        from dashboard_api import query_reach  # noqa: E402

        if not (HERE / "docs" / "index.json").is_file():
            self.skipTest("index.json missing")
        result = query_reach("scan.py", depth=1)
        self.assertIn("reachable", result)


class ApproveIssueTests(unittest.TestCase):
    @patch("dashboard_api.subprocess.run")
    def test_adds_labels(self, mock_run):
        mock_run.return_value.returncode = 0
        result, err = approve_issue("owner/repo", 21, auto_merge=True)
        self.assertIsNone(err)
        self.assertEqual(result["labels_added"], ["radar:approved", "radar:auto-merge"])
        self.assertEqual(result["labels_removed"], ["radar:proposed"])
        cmd = mock_run.call_args[0][0]
        self.assertIn("issue", cmd)
        self.assertIn("edit", cmd)
        self.assertIn("--remove-label", cmd)
        self.assertIn("--add-label", " ".join(cmd))


if __name__ == "__main__":
    unittest.main()
