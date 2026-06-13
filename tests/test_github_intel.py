import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from github_intel import (  # noqa: E402
    link_issues_to_prs,
    parse_issue_numbers,
    remote_repo_slug,
)


class ParseIssueNumbersTests(unittest.TestCase):
    def test_closes_in_body(self):
        body = "Implements the change.\n\nCloses #7"
        self.assertEqual(parse_issue_numbers("fix: #7 title", body, "issue-7"), [7])

    def test_title_and_branch(self):
        nums = parse_issue_numbers("fix: #12 something", "", "issue-12")
        self.assertEqual(nums, [12])

    def test_multiple_sources(self):
        body = "Fixes #3 and related work"
        nums = parse_issue_numbers("fix: #3", body, "feature-x")
        self.assertIn(3, nums)


class LinkIssuesTests(unittest.TestCase):
    def test_reverse_links(self):
        prs = [{"number": 14, "issue_numbers": [7]}]
        issues = [{"number": 7, "title": "t", "state": "CLOSED", "labels": [], "linked_prs": []}]
        linked = link_issues_to_prs(prs, issues)
        self.assertEqual(linked[0]["linked_prs"], [14])


class RemoteRepoSlugTests(unittest.TestCase):
    def test_parses_https_origin(self):
        slug = remote_repo_slug(HERE)
        self.assertIsNotNone(slug)
        self.assertIn("/", slug)


class DashboardFixtureTests(unittest.TestCase):
    def test_fixture_has_pr_schema(self):
        fixture = json.loads((HERE / "tests" / "fixtures" / "index_with_prs.json").read_text())
        self.assertEqual(fixture["schema_version"], 2)
        pr = fixture["pull_requests"][0]
        for key in ("number", "title", "issue_numbers", "commits", "files"):
            self.assertIn(key, pr)
        commit = pr["commits"][0]
        self.assertIn("files", commit)

    def test_pipeline_schema_optional(self):
        fixture = json.loads((HERE / "tests" / "fixtures" / "index_with_prs.json").read_text())
        pipeline = {
            "stages": [{"id": "proposed", "label": "Proposed", "order": 0}],
            "edges": [],
            "tickets": [{"issue_number": 1, "stage": "proposed", "stage_label": "Proposed"}],
        }
        fixture["pipeline"] = pipeline
        tmpl = (HERE / "templates" / "dashboard.html.tmpl").read_text()
        html = tmpl.replace("/*__DATA__*/", json.dumps(fixture))
        self.assertIn('"pipeline"', html)
        self.assertIn('pipelineBoard', html)

    def test_dashboard_template_injects_json(self):
        tmpl = (HERE / "templates" / "dashboard.html.tmpl").read_text()
        fixture = json.loads((HERE / "tests" / "fixtures" / "index_with_prs.json").read_text())
        html = tmpl.replace("/*__DATA__*/", json.dumps(fixture))
        self.assertIn('"pull_requests"', html)
        self.assertIn('"schema_version":2', html.replace(" ", ""))
        self.assertNotIn("/*__DATA__*/", html)


class ServeDashboardTests(unittest.TestCase):
    def test_build_local_dashboard_sets_meta(self):
        import serve_dashboard

        if not (HERE / "docs" / "index.json").is_file():
            self.skipTest("docs/index.json missing")
        html = serve_dashboard.build_local_dashboard()
        self.assertIn('"local_chat":true', html.replace(" ", ""))
        self.assertIn('"local_actions":true', html.replace(" ", ""))

    def test_summarize_context(self):
        import serve_dashboard

        if not (HERE / "docs" / "index.json").is_file():
            self.skipTest("docs/index.json missing")
        summary = serve_dashboard.summarize_context()
        self.assertIn("Repo:", summary)


if __name__ == "__main__":
    unittest.main()
