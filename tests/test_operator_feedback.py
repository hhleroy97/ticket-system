import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys_path = HERE / "scripts"
import sys

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(sys_path))

from operator_feedback import (  # noqa: E402
    append_feedback,
    filter_and_rank_findings,
    load_feedback,
    rejection_count,
    score_finding,
    should_skip_finding,
    titles_similar,
)
from request_issue import build_body, build_title, create_request_issue  # noqa: E402


class OperatorFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "feedback.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_load(self):
        append_feedback("approved", "Add reach UI", path=self.path, issue_number=1)
        entries = load_feedback(self.path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["action"], "approved")

    def test_skip_after_two_rejections(self):
        title = "Stale High-Churn Modules With Quiet Dependents"
        append_feedback("dismissed", title, path=self.path)
        append_feedback("dismissed", title, path=self.path)
        entries = load_feedback(self.path)
        self.assertTrue(should_skip_finding(title, entries))
        self.assertEqual(score_finding(title, entries), -1000)

    def test_titles_similar_substring(self):
        self.assertTrue(titles_similar(
            "Dependency Graph Has No Edges",
            "Dependency Graph Is Sparse",
        ))

    def test_filter_and_rank_boosts_approved_theme(self):
        append_feedback("approved", "Improve dashboard reach panel", path=self.path)
        candidates = [
            {"title": "Improve dashboard reach panel details"},
            {"title": "Unrelated finding about hooks"},
        ]
        ranked = filter_and_rank_findings(candidates, load_feedback(self.path))
        self.assertEqual(ranked[0]["title"], "Improve dashboard reach panel details")
        self.assertGreater(
            score_finding(ranked[0]["title"], load_feedback(self.path)),
            score_finding(ranked[1]["title"], load_feedback(self.path)),
        )


class RequestIssueTests(unittest.TestCase):
    def test_build_title_adds_request_prefix(self):
        self.assertTrue(build_title("Add author edges").startswith("request:"))

    def test_build_body_includes_acceptance(self):
        body = build_body("Do the thing", acceptance="Tests pass")
        self.assertIn("**Request:**", body)
        self.assertIn("Tests pass", body)

    def test_dry_run_no_gh(self):
        result, err = create_request_issue("owner/repo", "Add KG-14", dry_run=True)
        self.assertIsNone(err)
        self.assertIn("radar:proposed", result["labels"])


if __name__ == "__main__":
    unittest.main()
