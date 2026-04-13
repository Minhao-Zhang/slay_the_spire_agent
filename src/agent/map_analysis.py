"""Enumerate Spire map paths from each immediate choice to the bottom row (pre-boss layer).

Nodes come from CommunicationMod ``game["map"]``: each has ``x``, ``y``, ``symbol``, and
``children`` (list of child node dicts with ``x``/``y``). **Goal nodes** are all nodes at
``y == max_y`` among the provided nodes (bottom map row). The act boss is implicit after that.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_SYMBOL_TO_BUCKET: dict[str, str] = {
    "M": "monster",
    "E": "elite",
    "R": "rest",
    "$": "shop",
    "?": "event",
    "T": "treasure",
}

def _sym_char(node: dict[str, Any]) -> str:
    s = node.get("symbol", "?")
    if s is None:
        return "?"
    t = str(s).strip()
    return t[0] if t else "?"


def _node_key(n: dict[str, Any]) -> tuple[int, int] | None:
    x, y = n.get("x"), n.get("y")
    if isinstance(x, int) and isinstance(y, int):
        return (x, y)
    return None


def _child_key(c: dict[str, Any]) -> tuple[int, int] | None:
    return _node_key(c)


def _bucket_for_symbol(ch: str) -> str | None:
    return _SYMBOL_TO_BUCKET.get(ch)


def _path_counts(symbols: list[str]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for ch in symbols:
        b = _bucket_for_symbol(ch)
        if b:
            out[b] += 1
    return dict(out)


def _notable_pairs(symbols: list[str]) -> set[str]:
    """Adjacent symbol pairs of interest (CommunicationMod single-char symbols)."""
    found: set[str] = set()
    for i in range(len(symbols) - 1):
        a, b = symbols[i], symbols[i + 1]
        if a == "E" and b == "R":
            found.add("elite→rest")
        elif a == "E" and b == "E":
            found.add("elite→elite")
        elif a == "R" and b == "E":
            found.add("rest→elite")
        elif a == "R" and b == "R":
            found.add("rest→rest")
    return found


def _pick_sample_path(paths: list[list[str]]) -> list[str]:
    """Prefer most R rests, then fewest elites, then lexicographic symbol tuple."""

    def score(path: list[str]) -> tuple[int, int, tuple[str, ...]]:
        rests = sum(1 for ch in path if ch == "R")
        elites = sum(1 for ch in path if ch == "E")
        return (rests, -elites, tuple(path))

    return max(paths, key=score) if paths else []


def analyze_map_paths(
    nodes: list[dict],
    current_node: dict | None,
    next_nodes: list[dict],
    boss_available: bool,
) -> list[dict[str, Any]]:
    """
    For each ``next_node``, enumerate simple paths from that node to any goal (max ``y``).

    Returns one dict per ``next_node`` with:
    - ``next_node``: ``{x, y, symbol}`` (from input)
    - ``path_count``: number of distinct paths to a goal
    - ``encounter_summary``: mean counts per bucket (``monster``, ``elite``, …), rounded
    - ``notable_sequences``: deduped interesting 2-node pattern labels
    - ``sample_path``: symbol list of the chosen representative path
    """
    del current_node  # reserved for future heuristics (e.g. boss tile quirks)
    del boss_available  # goals are bottom row; flag unused for now

    if not nodes or not next_nodes:
        return []

    by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for n in nodes:
        k = _node_key(n)
        if k is not None:
            by_key[k] = n

    if not by_key:
        return []

    max_y = max(k[1] for k in by_key)
    goals = {k for k in by_key if k[1] == max_y}

    adj: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for k, n in by_key.items():
        for c in n.get("children") or []:
            ck = _child_key(c) if isinstance(c, dict) else None
            if ck is not None and ck in by_key:
                adj[k].append(ck)

    results: list[dict[str, Any]] = []

    for raw_next in next_nodes:
        if not isinstance(raw_next, dict):
            continue
        nk = _node_key(raw_next)
        if nk is None or nk not in by_key:
            results.append(
                {
                    "next_node": {
                        "x": raw_next.get("x"),
                        "y": raw_next.get("y"),
                        "symbol": raw_next.get("symbol", "?"),
                    },
                    "path_count": 0,
                    "encounter_summary": {},
                    "notable_sequences": [],
                    "sample_path": [],
                }
            )
            continue

        all_paths: list[list[str]] = []

        def dfs(pos: tuple[int, int], visited: frozenset[tuple[int, int]], syms: list[str]) -> None:
            if pos in goals:
                all_paths.append(list(syms))
                return
            for nxt in adj.get(pos, ()):
                if nxt in visited:
                    continue
                node = by_key.get(nxt)
                if node is None:
                    continue
                dfs(nxt, visited | {nxt}, syms + [_sym_char(node)])

        start_sym = _sym_char(by_key[nk])
        dfs(nk, frozenset({nk}), [start_sym])

        path_count = len(all_paths)
        notable: set[str] = set()
        for p in all_paths:
            notable |= _notable_pairs(p)

        encounter_summary: dict[str, int] = {}
        if all_paths:
            keys = {"monster", "elite", "rest", "shop", "event", "treasure"}
            for key in keys:
                vals = [_path_counts(p).get(key, 0) for p in all_paths]
                if any(v > 0 for v in vals):
                    mean = sum(vals) / len(vals)
                    encounter_summary[key] = int(mean + 0.5)  # half-up, stable for small ints

        sample = _pick_sample_path(all_paths)

        results.append(
            {
                "next_node": {
                    "x": raw_next.get("x"),
                    "y": raw_next.get("y"),
                    "symbol": raw_next.get("symbol", "?"),
                },
                "path_count": path_count,
                "encounter_summary": encounter_summary,
                "notable_sequences": sorted(notable),
                "sample_path": sample,
            }
        )

    return results
