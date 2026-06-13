import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
VERIFY = HERE / "scripts" / "verify_executor_branch.sh"
EXECUTOR_MD = HERE / ".github" / "EXECUTOR.md"


class ExecutorTests(unittest.TestCase):
    def test_verify_script_is_executable(self):
        self.assertTrue(VERIFY.is_file())
        subprocess.run(["bash", "-n", str(VERIFY)], check=True)

    def test_executor_instructions_exist(self):
        self.assertTrue(EXECUTOR_MD.is_file())
        text = EXECUTOR_MD.read_text()
        self.assertIn("One commit per logical change", text)
        self.assertIn("run_tests.py", text)


if __name__ == "__main__":
    unittest.main()
