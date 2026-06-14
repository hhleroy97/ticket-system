#!/usr/bin/env python3
"""BFS reach queries over docs/index.json provenance graph (stdlib)."""

import argparse
import json
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
INDEX = HERE / "docs" / "index.json"

DEFAULT_EDGE_TYPES = ("imports", "co_changed", "modifies", "contains")


def load_graph():
    if not INDEX.is_file():
        sys.exit(f"error: missing {INDEX}")
    index = json.loads(INDEX.read_text())
    graph = index.get("graph") or {}
    return graph.get("nodes") or [], graph.get("edges") or []


def build_adjacency(edges, edge_types, undirected=False):
    adj = {}
    for edge in edges:
        if edge.get("type") not in edge_types:
            continue
        src, tgt = edge["source"], edge["target"]
        adj.setdefault(src, []).append((tgt, edge))
        if undirected:
            adj.setdefault(tgt, []).append((src, edge))
    return adj


def bfs(start_id, adj, max_depth):
    visited = {start_id: (0, None)}
    queue = deque([(start_id, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for nxt, edge in adj.get(node, []):
            if nxt in visited:
                continue
            visited[nxt] = (depth + 1, edge)
            queue.append((nxt, depth + 1))
    return visited


def resolve_start(nodes, path_or_id):
    if path_or_id.startswith(("file:", "commit:", "pr:", "issue:", "run:")):
        return path_or_id
    path = path_or_id
    for node in nodes:
        if node.get("kind") == "file" and node.get("path") == path:
            return node["id"]
    return f"file:{path}"


def main():
    parser = argparse.ArgumentParser(description="Reach query on provenance graph")
    parser.add_argument("--from", dest="start", required=True, help="file path or node id")
    parser.add_argument("--depth", type=int, default=2, help="max BFS depth")
    parser.add_argument(
        "--edges",
        default=",".join(DEFAULT_EDGE_TYPES),
        help="comma-separated edge types",
    )
    parser.add_argument("--undirected", action="store_true", help="traverse both directions")
    args = parser.parse_args()

    nodes, edges = load_graph()
    node_by_id = {n["id"]: n for n in nodes}
    edge_types = tuple(t.strip() for t in args.edges.split(",") if t.strip())
    start = resolve_start(nodes, args.start)
    if start not in node_by_id:
        sys.exit(f"error: start node not found: {start}")

    adj = build_adjacency(edges, edge_types, undirected=args.undirected)
    visited = bfs(start, adj, args.depth)
    results = []
    for nid, (depth, edge) in sorted(visited.items(), key=lambda x: x[1][0]):
        if nid == start:
            continue
        node = node_by_id.get(nid, {"id": nid})
        via = edge["type"] if edge else ""
        label = node.get("path") or node.get("message") or node.get("title") or nid
        results.append({"id": nid, "kind": node.get("kind"), "depth": depth, "via": via, "label": label})

    print(json.dumps({"start": start, "depth": args.depth, "reachable": results}, indent=2))


if __name__ == "__main__":
    main()
