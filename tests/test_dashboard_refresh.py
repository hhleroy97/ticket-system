import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from dashboard_refresh import read_index_payload, refresh_intel_once  # noqa: E402


class DashboardRefreshTests(unittest.TestCase):
    def test_read_index_payload_shape(self):
        if not (HERE / "docs" / "index.json").is_file():
            self.skipTest("index.json missing")
        payload = read_index_payload()
        for key in ("repo", "stats", "pull_requests", "issues"):
            self.assertIn(key, payload)

    @patch("dashboard_refresh.refresh_github_intel")
    def test_refresh_intel_once(self, mock_intel):
        mock_intel.return_value = (True, "ok")
        ok, msg = refresh_intel_once()
        self.assertTrue(ok)
        self.assertEqual(msg, "ok")


if __name__ == "__main__":
    unittest.main()
