import json
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCAN = HERE / "scan.py"
FIXTURE = HERE / "test-repos" / "srcpkg"


class ScanTests(unittest.TestCase):
    def run_scan(self, target):
        env = {"TARGET_REPO": str(target)}
        proc = subprocess.run(
            ["python3", str(SCAN)],
            capture_output=True, text=True, cwd=HERE, env={**dict(**__import__("os").environ), **env},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        return json.loads((HERE / "docs" / "index.json").read_text())

    def test_src_layout_import_edges(self):
        index = self.run_scan(FIXTURE)
        edges = {(e["source"], e["target"]) for e in index["edges"]}
        self.assertIn(
            ("tests/test_core.py", "src/mypkg/core.py"),
            edges,
            f"expected test->core edge; got {sorted(edges)}",
        )
        self.assertEqual(index.get("package_roots"), {"": "src"})

    def test_sqlite_output(self):
        self.run_scan(FIXTURE)
        db = HERE / "docs" / "index.db"
        self.assertTrue(db.is_file())
        import sqlite3
        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
