#!/usr/bin/env python3
"""BFS reach queries over docs/index.json provenance graph (stdlib)."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))

from graph_lib import reach_query  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Reach query on provenance graph")
    parser.add_argument("--from", dest="start", required=True, help="file path or node id")
    parser.add_argument("--depth", type=int, default=2, help="max BFS depth")
    parser.add_argument(
        "--index",
        default=None,
        help="path to index.json (default: docs/index.json)",
    )
    parser.add_argument("--undirected", action="store_true", help="traverse both directions")
    args = parser.parse_args()

    index_path = Path(args.index) if args.index else None
    if index_path and not index_path.is_file():
        sys.exit(f"error: missing {index_path}")

    from graph_lib import load_index  # noqa: E402

    index = load_index(index_path)
    result = reach_query(args.start, depth=args.depth, index=index, undirected=args.undirected)
    if result.pop("missing", False):
        sys.exit(f"error: start node not found: {result['start']}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
