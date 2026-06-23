"""graphify adapter — plug graphmine co-change findings into a graphify graph.

Additive and non-destructive: the original nodes/edges are untouched; we only
append typed ``co_changes_with`` edges between graphify's *file* nodes, carrying
a new ``STATISTICAL`` confidence tier with the corrected q-value as the score.
Because they are a distinct relation, a consumer can filter them in or out and
never confuses temporal coupling with a structural code dependency.

graphmine never imports graphify; this adapter only reads/writes a graph.json.
"""
from __future__ import annotations

import json

from ..encoders.base import Encoding
from ..postprocess import Coupling


def _norm(p: str | None) -> str:
    return (p or "").replace("\\", "/").lstrip("./")


def file_node_index(graph: dict) -> dict[str, str]:
    """Map normalized source_file -> graphify *file* node id.

    A file node is the node that represents the file itself: it has a source_file
    but no source_location (symbols carry a line; the file node does not).
    """
    idx: dict[str, str] = {}
    for n in graph.get("nodes", []):
        sf = n.get("source_file")
        if sf and n.get("source_location") in (None, "", "null"):
            idx.setdefault(_norm(sf), n["id"])
    return idx


def augment_graph(graph: dict, enc: Encoding, couplings: list[Coupling]) -> dict:
    """Return graph copy with additive co_changes_with edges. Stats in graph
    ``["meta"]["graphmine"]``: how many couplings mapped onto file nodes."""
    idx = file_node_index(graph)
    lab = enc.id_label
    out = {**graph, "nodes": list(graph.get("nodes", [])),
           "edges": list(graph.get("edges", []))}
    added = 0
    unmapped = 0
    for c in couplings:
        sa, sb = idx.get(_norm(lab[c.a])), idx.get(_norm(lab[c.b]))
        if not sa or not sb:
            unmapped += 1
            continue
        q = c.p_adj if c.p_adj is not None else c.p_raw
        out["edges"].append({
            "source": sa, "target": sb, "relation": "co_changes_with",
            "confidence": "STATISTICAL", "confidence_score": q, "p_raw": c.p_raw,
            "weight": 1.0,
        })
        added += 1
    meta = dict(out.get("meta", {}))
    meta["graphmine"] = {"co_changes_with_added": added, "unmapped_couplings": unmapped,
                         "of_total": len(couplings)}
    out["meta"] = meta
    return out


def write_augmented(graph_json_path: str, enc: Encoding, couplings: list[Coupling],
                    out_path: str) -> dict:
    graph = json.loads(open(graph_json_path, encoding="utf-8").read())
    aug = augment_graph(graph, enc, couplings)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(aug, f)
    return aug["meta"]["graphmine"]
