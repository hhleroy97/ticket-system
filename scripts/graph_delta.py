#!/usr/bin/env python3
"""Verify branch commits appear in provenance graph modifies edges (stdlib + git)."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from graph_lib import file_node_id, load_index, load_provenance  # noqa: E402


def git(*args):
    return subprocess.run(
        ["git", "-C", str(HERE), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def branch_commit_shas(base: str, head: str = "HEAD") -> set[str]:
    proc = git("log", f"{base}..{head}", "--format=%H")
    if proc.returncode != 0:
        return set()
    full = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    short = {sha[:7] for sha in full}
    return full | short


def changed_files(base: str, head: str = "HEAD") -> list[str]:
    proc = git("diff", "--name-only", f"{base}...{head}")
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def modifies_map(edges) -> dict[str, set[str]]:
    """Map file path -> commit short shas that modify it."""
    out = {}
    for edge in edges:
        if edge.get("type") != "modifies" or not edge.get("target", "").startswith("file:"):
            continue
        path = edge["target"][5:]
        commit = edge["source"]
        if not commit.startswith("commit:"):
            continue
        out.setdefault(path, set()).add(commit.split(":", 1)[1])
    return out


def verify_graph_delta(base: str, head: str = "HEAD", index_path: Path | None = None) -> tuple[bool, str, dict]:
    index = load_index(index_path)
    graph = index.get("graph")
    if not graph:
        return True, "skip: index has no provenance graph (run github_intel.py)", {"skipped": True}

    _, edges, _ = load_provenance(index)
    branch_shas = branch_commit_shas(base, head)
    if not branch_shas:
        return True, "skip: no commits on branch ahead of base", {"skipped": True}

    mods = modifies_map(edges)
    code_files = [
        path
        for path in changed_files(base, head)
        if not path.startswith("docs/") and not path.startswith(".github/")
    ]
    if not code_files:
        return True, "skip: no non-doc files changed", {"skipped": True}

    missing = []
    for path in code_files:
        commit_ids = mods.get(path, set())
        if not commit_ids & branch_shas:
            missing.append(path)

    detail = {
        "base": base,
        "head": head,
        "code_files": code_files,
        "missing_modifies": missing,
        "branch_commits": len(branch_shas),
    }
    if missing:
        return (
            False,
            f"missing modifies edges for branch commits on: {', '.join(missing)}",
            detail,
        )
    return True, f"provenance ok for {len(code_files)} code file(s)", detail


def main():
    parser = argparse.ArgumentParser(description="Verify graph modifies edges for branch commits")
    parser.add_argument("--base", default="main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--index", default=None, help="path to index.json")
    args = parser.parse_args()

    index_path = Path(args.index) if args.index else None
    ok, msg, detail = verify_graph_delta(args.base, args.head, index_path)
    print(json.dumps({"ok": ok, "message": msg, **detail}, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
