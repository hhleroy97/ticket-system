import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from post_agent_progress import progress_body, should_post  # noqa: E402


class PostAgentProgressTests(unittest.TestCase):
    def test_should_post_on_change(self):
        state = {"last_commit_count": 0, "last_file_count": 0}
        self.assertTrue(should_post(state, 1, 2))

    def test_skip_when_unchanged(self):
        state = {"last_commit_count": 2, "last_file_count": 3}
        self.assertFalse(should_post(state, 2, 3))

    def test_progress_body_includes_counts(self):
        body = progress_body(21, {"commit_count": 2, "file_count": 5, "commits": []})
        self.assertIn("#21", body)
        self.assertIn("**2**", body)


if __name__ == "__main__":
    unittest.main()
