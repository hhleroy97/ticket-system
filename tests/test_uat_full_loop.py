import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

import uat_full_loop  # noqa: E402


def _fake_smoke_steps(report: uat_full_loop.UatReport):
    report.add("tests", "pass", "mocked")
    report.add("scan_intel_docgen", "skip", "mocked")
    report.add("radar_report", "pass", "mocked")
    report.add("parse_findings", "pass", "mocked")
    report.add("provenance_docgen", "pass", "mocked")
    report.add("graph_delta", "pass", "mocked")


class UatSmokeTests(unittest.TestCase):
    @patch.object(uat_full_loop, "step_graph_delta")
    @patch.object(uat_full_loop, "step_provenance_docgen")
    @patch.object(uat_full_loop, "step_parse_findings")
    @patch.object(uat_full_loop, "step_radar_report", return_value=None)
    @patch.object(uat_full_loop, "step_scan_intel_docgen")
    @patch.object(uat_full_loop, "step_tests")
    def test_smoke_invokes_pipeline_steps(
        self,
        mock_tests,
        mock_scan,
        mock_radar,
        mock_parse,
        mock_prov,
        mock_delta,
    ):
        uat_full_loop.run_smoke(refresh=False)
        mock_tests.assert_called_once()
        mock_scan.assert_called_once()
        mock_radar.assert_called_once()
        mock_parse.assert_called_once()
        mock_prov.assert_called_once()
        mock_delta.assert_called_once()

    def test_report_to_dict(self):
        report = uat_full_loop.UatReport("smoke")
        report.add("demo", "pass", "ok")
        data = report.to_dict()
        self.assertTrue(data["ok"])
        self.assertEqual(data["steps"][0]["name"], "demo")

    @patch.object(uat_full_loop, "run_smoke")
    @patch.object(uat_full_loop, "gh_available", return_value=False)
    def test_dry_run_fails_gh_when_unavailable(self, _gh, mock_smoke):
        mock_smoke.return_value = uat_full_loop.UatReport("smoke")
        _fake_smoke_steps(mock_smoke.return_value)
        report = uat_full_loop.run_dry_run(refresh=False)
        gh = next(s for s in report.steps if s.name == "gh_auth")
        self.assertEqual(gh.status, "fail")


class UatParseTests(unittest.TestCase):
    def test_parse_sample_radar_section(self):
        sample = (
            "## Example Finding\n"
            "**Files:** `scan.py`\n"
            "**Rationale:** test rationale here.\n\n"
        )
        findings = uat_full_loop.parse_findings(sample)
        self.assertEqual(len(findings), 1)
        self.assertIn("scan.py", findings[0]["files"])


if __name__ == "__main__":
    unittest.main()
