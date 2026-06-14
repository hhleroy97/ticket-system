#!/usr/bin/env python3
"""Shared provenance graph helpers (stdlib only)."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

DEFAULT_EDGE_TYPES = ("imports", "co_changed", "modifies", "contains", "authored")


def load_index(index_path: Path | str | None = None) -> dict:
    path = Path(index_path) if index_path else Path(__file__).resolve().parent.parent / "docs" / "index.json"
    return json.loads(path.read_text())


def load_provenance(index: dict | None = None, index_path: Path | str | None = None):
    if index is None:
        index = load_index(index_path)
    graph = index.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_by_id = {n["id"]: n for n in nodes}
    return nodes, edges, node_by_id


def file_node_id(path: str) -> str:
    return f"file:{path}"


def build_adjacency(edges, edge_types=DEFAULT_EDGE_TYPES, undirected=False):
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


def resolve_file_node(path_or_id: str, node_by_id: dict) -> str | None:
    if path_or_id.startswith("file:"):
        return path_or_id if path_or_id in node_by_id else None
    node_id = file_node_id(path_or_id)
    return node_id if node_id in node_by_id else None


def co_change_neighbors(path: str, edges, min_weight: int = 1) -> list[tuple[str, int]]:
    neighbors = {}
    fid = file_node_id(path)
    for edge in edges:
        if edge.get("type") != "co_changed":
            continue
        src, tgt = edge["source"], edge["target"]
        weight = edge.get("weight") or 1
        if weight < min_weight:
            continue
        if src == fid and tgt.startswith("file:"):
            neighbors[tgt[5:]] = max(neighbors.get(tgt[5:], 0), weight)
        elif tgt == fid and src.startswith("file:"):
            neighbors[src[5:]] = max(neighbors.get(src[5:], 0), weight)
    return sorted(neighbors.items(), key=lambda x: (-x[1], x[0]))


def authors_for_file(path: str, edges, node_by_id: dict, limit: int = 10) -> list[tuple[str, int]]:
    fid = file_node_id(path)
    authors = {}
    for edge in edges:
        if edge.get("type") != "authored" or edge.get("target") != fid:
            continue
        node = node_by_id.get(edge["source"])
        if not node or node.get("kind") != "author":
            continue
        label = node.get("name") or node.get("email") or edge["source"]
        weight = edge.get("weight") or 1
        authors[label] = max(authors.get(label, 0), weight)
    return sorted(authors.items(), key=lambda x: (-x[1], x[0]))[:limit]


def commits_for_file(path: str, edges, node_by_id: dict, limit: int = 5) -> list[dict]:
    fid = file_node_id(path)
    commits = []
    for edge in edges:
        if edge.get("type") != "modifies" or edge.get("target") != fid:
            continue
        node = node_by_id.get(edge["source"])
        if node and node.get("kind") == "commit":
            commits.append(node)
    commits.sort(key=lambda c: c.get("date") or "", reverse=True)
    return commits[:limit]


def reach_query(path: str, depth: int = 2, index: dict | None = None, undirected: bool = True) -> dict:
    nodes, edges, node_by_id = load_provenance(index)
    start = resolve_file_node(path, node_by_id)
    if not start:
        return {"start": file_node_id(path), "depth": depth, "reachable": [], "missing": True}
    adj = build_adjacency(edges, DEFAULT_EDGE_TYPES, undirected=undirected)
    visited = bfs(start, adj, depth)
    results = []
    for nid, (d, edge) in sorted(visited.items(), key=lambda x: x[1][0]):
        if nid == start:
            continue
        node = node_by_id.get(nid, {"id": nid})
        via = edge["type"] if edge else ""
        label = node.get("path") or node.get("message") or node.get("title") or nid
        results.append({"id": nid, "kind": node.get("kind"), "depth": d, "via": via, "label": label})
    return {"start": start, "depth": depth, "reachable": results, "missing": False}


def provenance_for_file(path: str, index: dict, reach_depth: int = 2) -> dict:
    _, edges, node_by_id = load_provenance(index)
    return {
        "commits": commits_for_file(path, edges, node_by_id),
        "authors": authors_for_file(path, edges, node_by_id),
        "co_changed": co_change_neighbors(path, edges),
        "reach": reach_query(path, depth=reach_depth, index=index),
    }
