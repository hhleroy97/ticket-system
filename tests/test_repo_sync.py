import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from repo_sync import get_state, run_sync, sync_once  # noqa: E402


class RepoSyncTests(unittest.TestCase):
    def test_sync_script_exists(self):
        self.assertTrue((HERE / "hooks" / "sync-origin-main.sh").is_file())

    @patch("repo_sync.subprocess.run")
    def test_run_sync_stay_flag(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "sync-origin-main: main already matches origin/main\n"
        ok, msg = run_sync(stay=True)
        self.assertTrue(ok)
        cmd = mock_run.call_args[0][0]
        self.assertIn("--stay", cmd)

    @patch("repo_sync.run_sync")
    @patch("repo_sync.git_branch_status")
    def test_sync_once_updates_state(self, mock_status, mock_run):
        mock_run.return_value = (True, "fast-forwarded")
        mock_status.return_value = {
            "branch": "main",
            "head": "abc1234",
            "origin_main": "abc1234",
            "behind": 0,
            "ahead": 0,
        }
        state = sync_once()
        self.assertTrue(state["ok"])
        self.assertEqual(state["head"], "abc1234")
        self.assertEqual(get_state()["head"], "abc1234")


if __name__ == "__main__":
    unittest.main()
