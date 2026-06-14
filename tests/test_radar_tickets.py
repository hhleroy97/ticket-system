import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts"))

from radar_ticket_lib import (
    is_duplicate,
    is_low_risk,
    labels_for_issue,
    select_issues,
)
import create_radar_issues
from draft_issues import validate_issue


class CreateRadarIssuesTests(unittest.TestCase):
    def test_validation_error_lists_issue_keys(self):
        err = create_radar_issues.validation_error({"title": "T"}, ["files"])
        self.assertIn("expected title, body, rationale, files", err)

    def test_candidates_from_report_parses_radar_shape(self):
        sample = """# RADAR 2026-06-13

## Stale High-Churn Modules With Quiet Dependents
**Files:** `draft_issues.py`, `docs/index.json`
**Rationale:** Hotspot module outpaces its importers.
"""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(sample)
            path = Path(fh.name)
        issues = create_radar_issues.candidates_from_report(path)
        path.unlink(missing_ok=True)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["title"], "Stale High-Churn Modules With Quiet Dependents")
        self.assertIn("draft_issues.py", issues[0]["files"])
        self.assertEqual(validate_issue(issues[0]), [])
        self.assertFalse(is_low_risk(issues[0]))


class RadarTicketLibTests(unittest.TestCase):
    def test_dedup_similar_titles(self):
        self.assertTrue(is_duplicate(
            "Improve dependency edge detection",
            ["Improve dependency edge detection in scan output"],
        ))

    def test_cap_at_three(self):
        candidates = [{"title": f"Issue {i}", "body": "", "files": "docs/a.md"} for i in range(10)]
        chosen = select_issues(candidates, [], limit=3)
        self.assertEqual(len(chosen), 3)

    def test_low_risk_docs_only(self):
        issue = {
            "title": "Update radar docs",
            "body": "**Files:** `docs/radar/README.md`",
            "files": "`docs/radar/README.md`",
        }
        self.assertTrue(is_low_risk(issue))
        labels = labels_for_issue(issue)
        self.assertIn("radar:auto-merge", labels)
        self.assertNotIn("radar:proposed", labels)

    def test_not_low_risk_workflow(self):
        issue = {
            "title": "Change CI",
            "body": "**Files:** `.github/workflows/radar.yml`",
            "files": "`.github/workflows/radar.yml`",
        }
        self.assertFalse(is_low_risk(issue))
        self.assertNotIn("radar:auto-merge", labels_for_issue(issue))

    def test_feedback_skips_deprioritized(self):
        from operator_feedback import append_feedback, filter_and_rank_findings, load_feedback
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fb.jsonl"
            title = "Stale High-Churn Modules With Quiet Dependents"
            append_feedback("dismissed", title, path=path)
            append_feedback("dismissed", title, path=path)
            candidates = [{"title": title}, {"title": "Other Finding"}]
            ranked = filter_and_rank_findings(candidates, load_feedback(path))
            self.assertEqual(len(ranked), 1)
            self.assertEqual(ranked[0]["title"], "Other Finding")


if __name__ == "__main__":
    unittest.main()
