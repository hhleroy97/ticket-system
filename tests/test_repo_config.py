import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from repo_config import (  # noqa: E402
    intel_root,
    resolve_docs,
    resolve_hook_scan_repo,
    resolve_target_repo,
)


class RepoConfigTests(unittest.TestCase):
    def test_intel_root_is_checkout(self):
        self.assertEqual(intel_root(), HERE.resolve())

    def test_hook_scan_ignores_target_env(self):
        with patch.dict(os.environ, {"TARGET_REPO": "/tmp/other-repo"}):
            self.assertEqual(resolve_hook_scan_repo(), HERE.resolve())

    def test_target_from_env(self):
        with patch.dict(os.environ, {"TARGET_REPO": str(HERE)}, clear=False):
            self.assertEqual(resolve_target_repo(), HERE.resolve())

    def test_docs_for_external_target_still_intel_docs(self):
        external = Path("/tmp/fake-repo")
        docs = resolve_docs(external)
        self.assertEqual(docs, HERE / "docs")


if __name__ == "__main__":
    unittest.main()
