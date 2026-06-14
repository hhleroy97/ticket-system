import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from cursor_agent import argv  # noqa: E402


class CursorAgentArgvTests(unittest.TestCase):
    def test_includes_force_for_headless_trust(self):
        cmd = argv("hello", model="composer-2.5")
        self.assertEqual(
            cmd,
            ["cursor-agent", "-p", "--force", "--model", "composer-2.5", "hello"],
        )

    def test_auto_model(self):
        cmd = argv("plan", model="auto")
        self.assertIn("--force", cmd)
        self.assertIn("auto", cmd)


if __name__ == "__main__":
    unittest.main()
