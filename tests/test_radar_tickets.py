import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from radar_ticket_lib import (
    is_duplicate,
    is_low_risk,
    labels_for_issue,
    select_issues,
)


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
        self.assertIn("radar:auto-merge", labels_for_issue(issue))

    def test_not_low_risk_workflow(self):
        issue = {
            "title": "Change CI",
            "body": "**Files:** `.github/workflows/radar.yml`",
            "files": "`.github/workflows/radar.yml`",
        }
        self.assertFalse(is_low_risk(issue))
        self.assertNotIn("radar:auto-merge", labels_for_issue(issue))


if __name__ == "__main__":
    unittest.main()
