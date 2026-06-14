import sys
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from resolve_pr_conflicts import (  # noqa: E402
    agent_enabled,
    assess_pr,
    can_auto_resolve,
    is_agent_eligible,
    is_regeneratable,
    split_conflicts,
)


class RegeneratablePathTests(unittest.TestCase):
    def test_exact_docs_artifacts(self):
        self.assertTrue(is_regeneratable("docs/index.json"))
        self.assertTrue(is_regeneratable("docs/dashboard.html"))

    def test_module_docs_prefix(self):
        self.assertTrue(is_regeneratable("docs/modules/scan-py.md"))

    def test_code_paths_not_regeneratable(self):
        self.assertFalse(is_regeneratable("scan.py"))
        self.assertFalse(is_regeneratable("scripts/pipeline_lib.py"))


class AutoResolvePolicyTests(unittest.TestCase):
    def test_all_docs_conflicts_auto_ok(self):
        ok, blocked = can_auto_resolve(
            ["docs/index.json", "docs/dashboard.html", "docs/modules/foo.md"]
        )
        self.assertTrue(ok)
        self.assertEqual(blocked, [])

    def test_code_conflict_blocks_auto(self):
        ok, blocked = can_auto_resolve(["docs/index.json", "scan.py"])
        self.assertFalse(ok)
        self.assertEqual(blocked, ["scan.py"])


class SplitConflictTests(unittest.TestCase):
    def test_split_docs_and_code(self):
        docs, code = split_conflicts(["docs/index.json", "scan.py", "docs/modules/x.md"])
        self.assertEqual(docs, ["docs/index.json", "docs/modules/x.md"])
        self.assertEqual(code, ["scan.py"])


class AgentEligibilityTests(unittest.TestCase):
    def test_blocks_workflow_conflicts(self):
        ok, reason = is_agent_eligible([".github/workflows/test.yml"])
        self.assertFalse(ok)
        self.assertIn("workflow", reason)

    def test_allows_code_conflicts(self):
        ok, _reason = is_agent_eligible(["scan.py", "scripts/foo.py"])
        self.assertTrue(ok)

    def test_blocks_too_many_files(self):
        files = [f"file{i}.py" for i in range(20)]
        ok, reason = is_agent_eligible(files)
        self.assertFalse(ok)
        self.assertIn("too many", reason)


class AgentEnabledTests(unittest.TestCase):
    def test_no_agent_flag(self):
        self.assertFalse(agent_enabled(False))

    def test_respects_env_disable(self):
        with unittest.mock.patch.dict("os.environ", {"CONFLICT_AGENT": "0", "CURSOR_API_KEY": "x"}):
            self.assertFalse(agent_enabled(None))


class AssessPrTests(unittest.TestCase):
    def test_mergeable_pr(self):
        item = assess_pr(
            {
                "number": 1,
                "title": "feat",
                "headRefName": "feat/x",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isCrossRepository": False,
                "isDraft": False,
            }
        )
        self.assertEqual(item.action, "ok")

    def test_conflicting_same_repo(self):
        item = assess_pr(
            {
                "number": 2,
                "title": "feat",
                "headRefName": "feat/y",
                "mergeable": "CONFLICTING",
                "mergeStateStatus": "DIRTY",
                "isCrossRepository": False,
                "isDraft": False,
            }
        )
        self.assertEqual(item.action, "conflict")

    def test_behind_same_repo(self):
        item = assess_pr(
            {
                "number": 4,
                "title": "behind",
                "headRefName": "feat/z",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "BEHIND",
                "isCrossRepository": False,
                "isDraft": False,
            }
        )
        self.assertEqual(item.action, "behind")

    def test_skips_fork(self):
        item = assess_pr(
            {
                "number": 3,
                "title": "fork",
                "headRefName": "patch",
                "mergeable": "CONFLICTING",
                "mergeStateStatus": "DIRTY",
                "isCrossRepository": True,
                "isDraft": False,
            }
        )
        self.assertEqual(item.action, "skip")
        self.assertIn("fork", item.detail)


if __name__ == "__main__":
    unittest.main()
