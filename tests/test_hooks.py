import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SYNC = HERE / "hooks" / "sync-origin-main.sh"
CURSOR_HOOK = HERE / ".cursor" / "hooks" / "post-pr-sync.sh"


class HookTests(unittest.TestCase):
    def test_sync_script_is_executable(self):
        self.assertTrue(SYNC.is_file())
        self.assertTrue(SYNC.stat().st_mode & 0o111)

    def test_sync_script_bash_syntax(self):
        subprocess.run(["bash", "-n", str(SYNC)], check=True)

    def test_cursor_hook_bash_syntax(self):
        subprocess.run(["bash", "-n", str(CURSOR_HOOK)], check=True)

    def test_hooks_json_exists(self):
        hooks_json = HERE / ".cursor" / "hooks.json"
        self.assertTrue(hooks_json.is_file())


if __name__ == "__main__":
    unittest.main()
