import json
import subprocess
import sys
import unittest
import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCAN = HERE / "scan.py"
FIXTURE = HERE / "test-repos" / "srcpkg"
FIXTURE_DOCS = FIXTURE / "docs"

sys.path.insert(0, str(HERE))
from scan import (
    discover_package_roots,
    eval_path_expr,
    git,
    parse_pyproject_package_dirs,
    python_dependency_edges,
    py_module_index,
)


class PathExprTests(unittest.TestCase):
    def test_eval_path_here_scripts(self):
        tree = ast.parse(
            "from pathlib import Path\n"
            "HERE = Path(__file__).resolve().parent.parent\n"
            "ROOT = str(HERE / 'scripts')\n"
        )
        const = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                val = eval_path_expr(node.value, const, HERE, "scripts/create_radar_issues.py")
                if val is not None:
                    const[node.targets[0].id] = val
        self.assertEqual(const["HERE"], ".")
        self.assertEqual(const["ROOT"], "scripts")


class PackageRootTests(unittest.TestCase):
    def test_pyproject_package_dir(self):
        self.assertEqual(parse_pyproject_package_dirs(FIXTURE), {"": "src"})

    def test_discover_src_layout(self):
        files = [f for f in git(FIXTURE, "ls-files").splitlines() if f]
        self.assertEqual(discover_package_roots(FIXTURE, files), {"": "src"})


class ScanTests(unittest.TestCase):
    def run_scan(self, target):
        env = {"TARGET_REPO": str(target)}
        proc = subprocess.run(
            ["python3", str(SCAN)],
            capture_output=True, text=True, cwd=HERE, env={**dict(**__import__("os").environ), **env},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        docs = FIXTURE_DOCS if target.resolve() == FIXTURE.resolve() else HERE / "docs"
        return json.loads((docs / "index.json").read_text())

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
        db = FIXTURE_DOCS / "index.db"
        self.assertTrue(db.is_file())
        import sqlite3
        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1)

    def test_primary_scan_excludes_fixture_paths(self):
        docs = HERE / "docs"
        tracked = [docs / "index.json", docs / "index.db", docs / "dashboard.html"]
        before = {p: (p.read_bytes() if p.is_file() else None) for p in tracked}
        try:
            index = self.run_scan(HERE)
            paths = {f["path"] for f in index["files"]}
            self.assertFalse(any(p.startswith("test-repos/") for p in paths))
        finally:
            for path, content in before.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)

    def test_sys_path_import_edges(self):
        files = [
            f for f in git(HERE, "ls-files").splitlines()
            if f and not f.startswith("test-repos/")
        ]
        modidx = py_module_index(files, {})
        edges = python_dependency_edges(
            HERE, "scripts/create_radar_issues.py", modidx, set(files)
        )
        self.assertIn("draft_issues.py", edges)
        self.assertIn("scripts/radar_ticket_lib.py", edges)

    def test_subprocess_python_edges(self):
        files = [
            f for f in git(HERE, "ls-files").splitlines()
            if f and not f.startswith("test-repos/")
        ]
        modidx = py_module_index(files, {})
        edges = python_dependency_edges(HERE, "tests/test_docgen.py", modidx, set(files))
        self.assertIn("scan.py", edges)
        self.assertIn("docgen.py", edges)
        self.assertIn("draft_issues.py", edges)

    def test_primary_dependency_graph_not_sparse(self):
        docs = HERE / "docs"
        tracked = [docs / "index.json", docs / "index.db", docs / "dashboard.html"]
        before = {p: (p.read_bytes() if p.is_file() else None) for p in tracked}
        try:
            index = self.run_scan(HERE)
            prod = [
                f for f in index["files"]
                if f["lang"] == "Python"
                and f["path"].endswith(".py")
                and not f["path"].startswith("tests/")
                and not f["path"].startswith("test-repos/")
                and not Path(f["path"]).name.startswith("test_")
            ]
            edge_count = index["stats"]["edge_count"]
            self.assertGreaterEqual(len(prod), 3)
            self.assertGreaterEqual(
                edge_count,
                len(prod) - 1,
                f"expected at least {len(prod) - 1} edges, got {edge_count}",
            )
        finally:
            for path, content in before.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
