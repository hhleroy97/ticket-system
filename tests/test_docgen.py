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
            capture_output=True,
            text=True,
            cwd=HERE,
            env={**__import__("os").environ, "TARGET_REPO": str(FIXTURE)},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        modules = list((FIXTURE_DOCS / "modules").glob("*.md"))
        self.assertGreaterEqual(len(modules), 1)

    def test_docgen_includes_provenance_when_graph_present(self):
        fixture_index = json.loads(
            (HERE / "tests" / "fixtures" / "index_with_graph.json").read_text()
        )
        docs = HERE / "docs"
        index_path = docs / "index.json"
        backup = index_path.read_text() if index_path.is_file() else None
        try:
            index_path.write_text(json.dumps(fixture_index, indent=2))
            proc = subprocess.run(
                ["python3", str(HERE / "docgen.py")],
                capture_output=True,
                text=True,
                cwd=HERE,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            alpha_doc = docs / "modules" / "alpha.md"
            self.assertTrue(alpha_doc.is_file(), alpha_doc)
            text = alpha_doc.read_text()
            self.assertIn("## Provenance", text)
            self.assertIn("Reach", text)
        finally:
            if backup is not None:
                index_path.write_text(backup)
            elif index_path.is_file():
                index_path.unlink(missing_ok=True)


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

    def test_parse_findings_with_graph_fields(self):
        sample = """## Co-change gap
**Files:** `a.py`
**Graph evidence:** co_change(3) on `a.py`
**Rationale:** needs tests
**Acceptance:** add test importing a.py
"""
        issues = parse_findings(sample)
        self.assertEqual(len(issues), 1)
        self.assertIn("co_change", issues[0]["graph_evidence"])
        self.assertIn("add test", issues[0]["acceptance"])
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
