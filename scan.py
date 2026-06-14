#!/usr/bin/env python3
"""
repo-intel scanner — deterministic, stdlib-only.

Walks a target git repo and emits:
  docs/index.json      structured repo state + import dependency graph
  docs/index.db        optional SQLite mirror for analytical queries
  docs/dashboard.html  standalone visualization (data inlined, open directly)

The agent is never invoked here. Scanning must be reproducible and free.

Target repo resolution order:
  1. TARGET_REPO environment variable
  2. TARGET_REPO=... line in a local .env file
  3. ./test-repos/click  (demo fallback)
"""

import ast
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = 2
FIXTURE_ROOT = HERE / "test-repos"

LANG_BY_EXT = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".rs": "Rust", ".go": "Go", ".java": "Java", ".rb": "Ruby", ".php": "PHP",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#", ".swift": "Swift", ".kt": "Kotlin", ".scala": "Scala",
    ".css": "CSS", ".scss": "CSS", ".html": "HTML", ".vue": "Vue", ".svelte": "Svelte",
    ".sh": "Shell", ".sql": "SQL", ".md": "Markdown", ".rst": "Docs",
    ".json": "Config", ".yaml": "Config", ".yml": "Config", ".toml": "Config", ".ini": "Config",
}
GRAPH_LANGS = {"Python", "JavaScript", "TypeScript"}
JS_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
JS_IMPORT = re.compile(
    r"""(?:import\s[^'"]*?from\s*|import\s*|require\(\s*|export\s[^'"]*?from\s*)['"]([^'"]+)['"]"""
)
IMPORTLIB_CALL = re.compile(
    r"""importlib\.import_module\s*\(\s*['"]([^'"]+)['"]"""
)
PYTHON_CMDS = frozenset({"python", "python3", "python3.10", "python3.11", "python3.12"})
SUBPROCESS_FUNCS = frozenset(
    {"run", "call", "Popen", "check_call", "check_output", "getoutput", "getstatusoutput"}
)
SETUP_PACKAGE_DIR = re.compile(
    r"""package_dir\s*=\s*\{([^}]+)\}""", re.DOTALL
)
SETUP_DIR_PAIR = re.compile(
    r"""['"]([^'"]*)['"]\s*:\s*['"]([^'"]+)['"]"""
)
PYPROJECT_PACKAGE_DIR = re.compile(
    r"""^\s*package[-_]dir\s*=\s*\{([^}]+)\}\s*$""", re.MULTILINE | re.IGNORECASE
)
PYPROJECT_FIND_WHERE = re.compile(
    r"""^\s*where\s*=\s*\[(.*?)\]\s*$""", re.MULTILINE
)
TOML_STRING = re.compile(r"""['"]([^'"]+)['"]""")


def resolve_target():
    target = os.environ.get("TARGET_REPO")
    if not target:
        env = HERE / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line.startswith("TARGET_REPO=") and not line.startswith("#"):
                    target = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not target:
        target = str(FIXTURE_ROOT / "click")
    return Path(target).expanduser().resolve()


def resolve_docs(repo):
    """Primary project docs live under docs/; fixture repos under <fixture>/docs/."""
    repo = repo.resolve()
    if repo == HERE.resolve():
        return HERE / "docs"
    try:
        repo.relative_to(FIXTURE_ROOT)
        return repo / "docs"
    except ValueError:
        return HERE / "docs"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, errors="replace",
    ).stdout


def is_git_repo(repo):
    return repo.is_dir() and git(repo, "rev-parse", "--is-inside-work-tree").strip() == "true"


def loc_of(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return sum(1 for _ in fh), False
    except (UnicodeDecodeError, OSError):
        return 0, True


def git_history(repo):
    """Single pass over history -> per-file churn (commit count) and last-touched date."""
    churn = defaultdict(int)
    last = {}
    out = git(repo, "log", "--no-merges", "--pretty=format:@@@%cs", "--name-only")
    date = None
    for line in out.splitlines():
        if line.startswith("@@@"):
            date = line[3:]
        elif line.strip():
            f = line.strip()
            churn[f] += 1
            last.setdefault(f, date)
    return churn, last


def _parse_package_dir_block(block):
    mapping = {}
    for m in SETUP_DIR_PAIR.finditer(block):
        prefix, root = m.group(1), m.group(2).strip().strip("/")
        mapping[prefix] = root
    return mapping


def parse_pyproject_package_dirs(repo):
    path = repo / "pyproject.toml"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    mapping = {}
    try:
        import tomllib
        data = tomllib.loads(text)
        tool = data.get("tool", {})
        setuptools = tool.get("setuptools", {})
        package_dir = setuptools.get("package-dir") or setuptools.get("package_dir")
        if isinstance(package_dir, dict):
            for prefix, root in package_dir.items():
                mapping[str(prefix)] = str(root).strip().strip("/")
        packages_find = setuptools.get("packages", {}).get("find", {})
        if isinstance(packages_find, dict):
            where = packages_find.get("where")
            if isinstance(where, list):
                for root in where:
                    mapping.setdefault("", str(root).strip().strip("/"))
            elif isinstance(where, str):
                mapping.setdefault("", where.strip().strip("/"))
    except Exception:
        m = PYPROJECT_PACKAGE_DIR.search(text)
        if m:
            mapping.update(_parse_package_dir_block(m.group(1)))
        section = re.search(
            r"\[tool\.setuptools\.packages\.find\](.*?)(?:\n\[|\Z)",
            text, re.DOTALL,
        )
        if section:
            wm = PYPROJECT_FIND_WHERE.search(section.group(1))
            if wm:
                for root in TOML_STRING.findall(wm.group(1)):
                    mapping.setdefault("", root.strip().strip("/"))
    return mapping


def parse_setup_package_dirs(repo):
    path = repo / "setup.py"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    m = SETUP_PACKAGE_DIR.search(text)
    return _parse_package_dir_block(m.group(1)) if m else {}


def discover_package_roots(repo, files):
    """
    Map package prefix -> filesystem root directory.
    Inspired by netimport/scaffoldr: honor pyproject/setup package_dir and src/ heuristics.
    """
    roots = {}
    roots.update(parse_setup_package_dirs(repo))
    roots.update(parse_pyproject_package_dirs(repo))

    tracked = set(files)
    if "" not in roots and (repo / "src").is_dir():
        src = "src"
        has_pkg = any(
            f.startswith(f"{src}/") and f.endswith("/__init__.py") for f in tracked
        )
        if has_pkg:
            roots[""] = src

    # Normalize and drop roots that do not exist in the tracked tree.
    normalized = {}
    for prefix, root in roots.items():
        root = root.strip().strip("/")
        if not root:
            continue
        if root in tracked or any(f.startswith(f"{root}/") for f in tracked):
            normalized[prefix] = root
    return normalized


def module_path_from_file(path):
    mod = path[:-3].replace("/", ".")
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    return mod


def py_module_index(files, package_roots):
    """Map dotted module path -> file path, including package-root aliases."""
    idx = {}
    for f in files:
        if not f.endswith(".py"):
            continue
        mod = module_path_from_file(f)
        idx[mod] = f

        for prefix, root in package_roots.items():
            root_prefix = f"{root}/"
            if not (f == root or f.startswith(root_prefix)):
                continue
            rel = f[len(root_prefix):] if f.startswith(root_prefix) else ""
            rel_mod = module_path_from_file(rel) if rel.endswith(".py") else ""
            if prefix:
                alias = f"{prefix}.{rel_mod}" if rel_mod else prefix
            else:
                alias = rel_mod
            if alias:
                idx[alias] = f
    return idx


def resolve_module(name, modidx):
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in modidx:
            return modidx[cand]
    return None


def _dirname(path):
    parent = os.path.dirname(path.replace("\\", "/"))
    return parent if parent else "."


def _repo_relative_path(repo, path):
    path = path.replace("\\", "/")
    repo_prefix = str(repo.resolve()).replace("\\", "/") + "/"
    if path.startswith(repo_prefix):
        return path[len(repo_prefix):]
    return os.path.normpath(path).replace("\\", "/")


def eval_path_expr(node, const, repo, rel_file):
    """Best-effort static evaluation of path-like expressions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _repo_relative_path(repo, node.value)
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return rel_file
        return const.get(node.id)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "str" and node.args:
            return eval_path_expr(node.args[0], const, repo, rel_file)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
            return eval_path_expr(node.func.value, const, repo, rel_file)
        if isinstance(node.func, ast.Name) and node.func.id == "Path" and node.args:
            return eval_path_expr(node.args[0], const, repo, rel_file)
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        base = eval_path_expr(node.value, const, repo, rel_file)
        return _dirname(base) if base else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = eval_path_expr(node.left, const, repo, rel_file)
        right = eval_path_expr(node.right, const, repo, rel_file)
        if left is not None and right is not None:
            return os.path.normpath(os.path.join(left, right)).replace("\\", "/")
    return None


def module_constants(tree, repo, rel_file):
    const = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                val = eval_path_expr(node.value, const, repo, rel_file)
                if val is not None:
                    const[target.id] = val
    return const


def sys_path_roots(tree, const, repo, rel_file):
    roots = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "sys"
            and func.value.attr == "path"
            and func.attr in ("insert", "append")
        ):
            continue
        if not node.args:
            continue
        resolved = eval_path_expr(node.args[-1], const, repo, rel_file)
        if resolved is not None:
            roots.append(resolved)
    return roots


def files_on_sys_path(fileset, root):
    root = (root or ".").strip("/") or "."
    if root == ".":
        return [f for f in fileset if f.endswith(".py") and "/" not in f]
    prefix = f"{root}/"
    return [f for f in fileset if f.endswith(".py") and f.startswith(prefix)]


def augment_modidx(modidx, fileset, extra_roots):
    idx = dict(modidx)
    for root in extra_roots:
        for f in files_on_sys_path(fileset, root):
            stem = os.path.basename(f)[:-3]
            idx.setdefault(stem, f)
            if "/" in f:
                rel = f[len(root) + 1:] if root != "." and f.startswith(f"{root}/") else f
                mod = module_path_from_file(rel)
                idx.setdefault(mod, f)
    return idx


def import_edges_from_tree(tree, rel_file, modidx):
    targets = set()
    pkg = module_path_from_file(rel_file)
    pkg = ".".join(pkg.split(".")[:-1]) if not rel_file.endswith("/__init__.py") else pkg

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                t = resolve_module(n.name, modidx)
                if t:
                    targets.add(t)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = pkg.split(".")[: len(pkg.split(".")) - (node.level - 1)] if pkg else []
                base = ".".join(filter(None, [".".join(up), base]))
            candidates = [base] if base else []
            if base:
                candidates.extend(f"{base}.{n.name}" for n in node.names)
            for cand in candidates:
                t = resolve_module(cand, modidx)
                if t:
                    targets.add(t)
    return targets


def py_edges(repo, f, modidx):
    try:
        tree = ast.parse((repo / f).read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return set()
    return import_edges_from_tree(tree, f, modidx)


def resolve_script_path(path, repo, rel_file, fileset):
    if not path or not str(path).endswith(".py"):
        return None
    path = _repo_relative_path(repo, str(path))
    candidates = [
        path,
        os.path.normpath(os.path.join(os.path.dirname(rel_file), path)).replace("\\", "/"),
        os.path.basename(path),
    ]
    for cand in candidates:
        if cand in fileset:
            return cand
        for tracked in fileset:
            if tracked.endswith(f"/{cand}") or os.path.basename(tracked) == cand:
                if tracked.endswith(".py"):
                    return tracked
    return None


def _is_subprocess_call(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            return func.attr in SUBPROCESS_FUNCS
    return False


def subprocess_py_edges(repo, f, fileset, tree, const):
    targets = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_call(node):
            continue
        if not node.args or not isinstance(node.args[0], (ast.List, ast.Tuple)):
            continue
        elements = node.args[0].elts
        if len(elements) < 2:
            continue
        cmd = eval_path_expr(elements[0], const, repo, f)
        if cmd not in PYTHON_CMDS:
            continue
        script = eval_path_expr(elements[1], const, repo, f)
        target = resolve_script_path(script, repo, f, fileset)
        if target:
            targets.add(target)
    return targets


def python_dependency_edges(repo, f, modidx, fileset):
    try:
        text = (repo / f).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except (SyntaxError, OSError):
        return set()
    const = module_constants(tree, repo, f)
    local_idx = augment_modidx(modidx, fileset, sys_path_roots(tree, const, repo, f))
    targets = import_edges_from_tree(tree, f, local_idx)
    for name in IMPORTLIB_CALL.findall(text):
        t = resolve_module(name, local_idx)
        if t:
            targets.add(t)
    targets |= subprocess_py_edges(repo, f, fileset, tree, const)
    return targets


def importlib_edges(repo, f, modidx):
    """Best-effort resolution of importlib.import_module('pkg.mod') string literals."""
    targets = set()
    try:
        text = (repo / f).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return targets
    for name in IMPORTLIB_CALL.findall(text):
        t = resolve_module(name, modidx)
        if t:
            targets.add(t)
    return targets


def load_tsconfig_paths(repo):
    """Return list of (pattern, targets[]) from nearest tsconfig.json."""
    configs = []
    for name in ("tsconfig.json", "tsconfig.base.json"):
        path = repo / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        compiler = data.get("compilerOptions", {})
        base_url = compiler.get("baseUrl", ".")
        paths = compiler.get("paths", {})
        if isinstance(paths, dict):
            configs.append((base_url, paths))
    return configs


def resolve_ts_alias(spec, repo, fileset, tsconfigs):
    if not tsconfigs or spec.startswith("."):
        return None
    for base_url, paths in tsconfigs:
        for pattern, targets in paths.items():
            star = pattern.endswith("*")
            prefix = pattern[:-1] if star else pattern
            if star:
                if not spec.startswith(prefix):
                    continue
                suffix = spec[len(prefix):]
            elif spec != pattern:
                continue
            else:
                suffix = ""
            for target in targets if isinstance(targets, list) else [targets]:
                repl = target[:-1] if target.endswith("*") else target
                cand = os.path.normpath(
                    os.path.join(base_url, repl + suffix if star else repl)
                ).replace("\\", "/")
                for guess in (
                    cand,
                    *[cand + e for e in JS_EXTS],
                    *[f"{cand}/index{e}" for e in JS_EXTS],
                ):
                    if guess in fileset:
                        return guess
    return None


def js_edges(repo, f, fileset, tsconfigs):
    targets = set()
    try:
        text = (repo / f).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return targets
    base = os.path.dirname(f)
    for spec in JS_IMPORT.findall(text):
        if spec.startswith("."):
            cand = os.path.normpath(os.path.join(base, spec))
            guesses = (
                cand,
                *[cand + e for e in JS_EXTS],
                *[f"{cand}/index{e}" for e in JS_EXTS],
            )
        else:
            alias = resolve_ts_alias(spec, repo, fileset, tsconfigs)
            guesses = (alias,) if alias else ()
        for guess in guesses:
            if guess in fileset:
                targets.add(guess)
                break
    return targets


def write_sqlite(index, path):
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE repo (
            name TEXT, path TEXT, branch TEXT, head TEXT,
            total_commits INTEGER, generated_at TEXT, schema_version INTEGER
        );
        CREATE TABLE stats (
            file_count INTEGER, total_loc INTEGER,
            contributor_count INTEGER, edge_count INTEGER
        );
        CREATE TABLE languages (name TEXT, files INTEGER, loc INTEGER);
        CREATE TABLE files (
            path TEXT PRIMARY KEY, lang TEXT, loc INTEGER, size INTEGER,
            commits INTEGER, last_commit TEXT
        );
        CREATE TABLE edges (source TEXT, target TEXT);
        """
    )
    r = index["repo"]
    cur.execute(
        "INSERT INTO repo VALUES (?,?,?,?,?,?,?)",
        (
            r["name"], r["path"], r["branch"], r["head"],
            r["total_commits"], r["generated_at"], index.get("schema_version", SCHEMA_VERSION),
        ),
    )
    s = index["stats"]
    cur.execute(
        "INSERT INTO stats VALUES (?,?,?,?)",
        (s["file_count"], s["total_loc"], s["contributor_count"], s["edge_count"]),
    )
    cur.executemany(
        "INSERT INTO languages VALUES (?,?,?)",
        [(l["name"], l["files"], l["loc"]) for l in index["languages"]],
    )
    cur.executemany(
        "INSERT INTO files VALUES (?,?,?,?,?,?)",
        [
            (f["path"], f["lang"], f["loc"], f["size"], f["commits"], f["last_commit"])
            for f in index["files"]
        ],
    )
    cur.executemany(
        "INSERT INTO edges VALUES (?,?)",
        [(e["source"], e["target"]) for e in index["edges"]],
    )
    conn.commit()
    conn.close()


DASHBOARD_TEMPLATE = HERE / "templates" / "dashboard.html.tmpl"
DATA_PLACEHOLDER = "/*__DATA__*/"


def render_dashboard(index):
    """Render standalone dashboard HTML with scan index inlined as JSON."""
    tmpl = DASHBOARD_TEMPLATE.read_text()
    return tmpl.replace(DATA_PLACEHOLDER, json.dumps(index))


def main():
    repo = resolve_target()
    if not is_git_repo(repo):
        sys.exit(f"error: {repo} is not a git repository (set TARGET_REPO)")

    files = list(dict.fromkeys(f for f in git(repo, "ls-files").splitlines() if f))
    if repo.resolve() == HERE.resolve():
        files = [f for f in files if not f.startswith("test-repos/")]
    fileset = set(files)
    churn, last = git_history(repo)
    package_roots = discover_package_roots(repo, files)
    modidx = py_module_index(files, package_roots)
    tsconfigs = load_tsconfig_paths(repo)

    file_records, lang_agg = [], defaultdict(lambda: {"files": 0, "loc": 0})
    edges = []
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        lang = LANG_BY_EXT.get(ext, "Other")
        loc, _binary = (0, True) if lang in ("Config",) else loc_of(repo / f)
        try:
            size = (repo / f).stat().st_size
        except OSError:
            size = 0
        rec = {
            "path": f, "lang": lang, "loc": loc, "size": size,
            "commits": churn.get(f, 0), "last_commit": last.get(f),
        }
        file_records.append(rec)
        lang_agg[lang]["files"] += 1
        lang_agg[lang]["loc"] += loc

        if lang == "Python":
            targets = python_dependency_edges(repo, f, modidx, fileset)
            for t in targets:
                if t != f:
                    edges.append({"source": f, "target": t})
        elif lang in ("JavaScript", "TypeScript"):
            for t in js_edges(repo, f, fileset, tsconfigs):
                if t != f:
                    edges.append({"source": f, "target": t})

    contributors = sorted(set(filter(None, git(repo, "log", "--pretty=format:%an").splitlines())))
    languages = sorted(
        ({"name": k, **v} for k, v in lang_agg.items()),
        key=lambda x: x["loc"], reverse=True,
    )
    index = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "intel_root": str(HERE.resolve()),
            "scan_target": str(repo.resolve()),
            "scan_target_is_self": repo.resolve() == HERE.resolve(),
        },
        "repo": {
            "name": repo.name,
            "path": str(repo),
            "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
            "head": git(repo, "rev-parse", "--short", "HEAD").strip(),
            "total_commits": int(git(repo, "rev-list", "--count", "HEAD").strip() or 0),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        },
        "package_roots": package_roots,
        "stats": {
            "file_count": len(file_records),
            "total_loc": sum(r["loc"] for r in file_records),
            "contributor_count": len(contributors),
            "edge_count": len(edges),
        },
        "languages": languages,
        "files": file_records,
        "edges": edges,
    }

    docs = resolve_docs(repo)
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "index.json").write_text(json.dumps(index, indent=2))
    write_sqlite(index, docs / "index.db")

    (docs / "dashboard.html").write_text(render_dashboard(index))

    s = index["stats"]
    print(f"scanned {index['repo']['name']} @ {index['repo']['head']}")
    print(f"  package roots: {package_roots or '(none)'}")
    print(f"  {s['file_count']} files, {s['total_loc']:,} LOC, "
          f"{s['edge_count']} import edges, {s['contributor_count']} contributors")
    print(f"  wrote {docs/'index.json'}, {docs/'index.db'}, and {docs/'dashboard.html'}")


if __name__ == "__main__":
    main()

# conflict-bot smoke marker (branch)
