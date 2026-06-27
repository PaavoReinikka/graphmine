"""Encoding B — co-reference. Transaction = a file; items = the cross-file
SYMBOLS it references (calls/imports/uses/...).

Symbols only (file-target nodes are excluded) to avoid the file⇔its-own-symbol
tautology. Static co-reference tends to be weaker/noisier than co-change; this
encoder exists for completeness and experimentation.
"""
from __future__ import annotations

import json
from collections import defaultdict

from .base import Encoding

_REF_RELS = {"calls", "imports", "imports_from", "uses", "references", "inherits", "method"}


def _subsystem(path: str | None, depth: int = 1) -> str:
    if not path:
        return "?"
    dirs = path.replace("\\", "/").split("/")[:-1]   # directory only (drop filename)
    if not dirs:
        return "(root)"
    return "/".join(dirs[:depth])


def encode(graph_json: str, *, min_freq: int = 2, max_freq_frac: float = 0.6,
           subsystem_depth: int = 1) -> Encoding:
    g = json.loads(open(graph_json, encoding="utf-8").read())
    nodes = {n["id"]: n for n in g["nodes"]}

    txn: dict[str, set[str]] = defaultdict(set)
    for e in g["edges"]:
        if e.get("relation") not in _REF_RELS:
            continue
        sn, tn = nodes.get(e.get("source")), nodes.get(e.get("target"))
        if not sn or not tn:
            continue
        sf, tf = sn.get("source_file"), tn.get("source_file")
        # symbols only: target must have a source_location (i.e. be a symbol, not a
        # file node) and live in a different file.
        if not sf or not tf or sf == tf or tn.get("source_location") is None:
            continue
        txn[sf].add(e["target"])

    n = len(txn)
    counts: dict[str, int] = defaultdict(int)
    for items in txn.values():
        for it in items:
            counts[it] += 1
    keep = {it for it, c in counts.items() if c >= min_freq and c <= max_freq_frac * n}

    iid = {it: i for i, it in enumerate(sorted(keep))}
    id_label = {i: nodes[it].get("label", it) for it, i in iid.items()}
    id_subsystem = {i: _subsystem(nodes[it].get("source_file"), subsystem_depth)
                    for it, i in iid.items()}

    transactions = []
    for items in txn.values():
        row = sorted(iid[it] for it in items if it in keep)
        if len(row) >= 2:
            transactions.append(row)

    return Encoding(transactions=transactions, id_label=id_label,
                    id_subsystem=id_subsystem,
                    meta={"encoder": "graph_coref", "graph": graph_json, "files": n})
