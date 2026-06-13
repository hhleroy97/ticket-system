import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FIXTURE = HERE / "test-repos" / "srcpkg"
FIXTURE_DOCS = FIXTURE / "docs"

import sys

sys.path.insert(0, str(HERE))
from draft_issues import ISSUE_KEYS, parse_findings, validate_issue


class DocgenTests(unittest.TestCase):
    def test_docgen_writes_modules(self):
        subprocess.run(
            ["python3", str(HERE / "scan.py")],
            check=True,
            cwd=HERE,
            env={**__import__("os").environ, "TARGET_REPO": str(FIXTURE)},
        )
        proc = subprocess.run(
            ["python3", str(HERE / "docgen.py")],
            capture_output=True, text=True, cwd=HERE,
            env={**__import__("os").environ, "TARGET_REPO": str(FIXTURE)},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        modules = list((FIXTURE_DOCS / "modules").glob("*.md"))
        self.assertGreaterEqual(len(modules), 1)


class DraftIssuesTests(unittest.TestCase):
    SAMPLE = """# RADAR 2026-06-13

## High churn in core module
**Files:** `src/mypkg/core.py`
**Rationale:** 42 commits with no tests touching imports.
"""

    def test_parse_findings(self):
        issues = parse_findings(self.SAMPLE)
        self.assertEqual(len(issues), 1)
        self.assertIn("core", issues[0]["title"])
        self.assertIn("core.py", issues[0]["files"])
        self.assertIn("commits", issues[0]["rationale"])
        self.assertEqual(validate_issue(issues[0]), [])

    def test_validate_issue_reports_missing_fields(self):
        self.assertEqual(validate_issue({"title": "x"}), ["body", "rationale", "files"])

    def test_cli_matches_parse_findings(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(self.SAMPLE)
            path = fh.name
        proc = subprocess.run(
            ["python3", str(HERE / "draft_issues.py"), path],
            capture_output=True,
            text=True,
            check=True,
        )
        issues = json.loads(proc.stdout)
        self.assertEqual(issues, parse_findings(self.SAMPLE))
        for item in issues:
            self.assertEqual(set(item), set(ISSUE_KEYS))


if __name__ == "__main__":
    unittest.main()
