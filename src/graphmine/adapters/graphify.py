"""graphify adapter — plug graphmine co-change findings into a graphify graph.

Additive and non-destructive: the original nodes/edges are untouched; we only
append typed ``co_changes_with`` edges between graphify's *file* nodes, carrying
a new ``STATISTICAL`` confidence tier with the raw Fisher p-value as the score.
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


def edge_key(graph: dict) -> str:
    """The key holding the edge list: graphify's graph.json (networkx node-link)
    uses ``links``; graphweave and raw extractions use ``edges``. Appending to the
    wrong one would silently add edges no graphify loader ever reads."""
    return "links" if "links" in graph and "edges" not in graph else "edges"


def _label_names_file(label: str | None, source_file: str) -> bool:
    # graphify's own file-node rule (build._is_file_node_label): the label is the
    # bare basename, or a directory-qualified suffix from its disambiguation pass.
    if not label:
        return False
    sf = source_file.replace("\\", "/")
    return label == sf.rsplit("/", 1)[-1] or (
        "/" in label and (sf == label or sf.endswith("/" + label)))


def file_node_index(graph: dict) -> dict[str, str]:
    """Map normalized source_file -> graphify *file* node id.

    A file node is the node that represents the file itself. graphify >= 0.9
    gives it ``source_location: "L1"`` and labels it with the file name, so the
    label is the reliable signal; older graphs left the location empty, which is
    kept as a fallback (label matches win, so a directory anchor or other
    location-less node sharing the source_file never shadows the file node).
    """
    idx: dict[str, str] = {}
    fallback: dict[str, str] = {}
    for n in graph.get("nodes", []):
        sf = n.get("source_file")
        if not sf:
            continue
        if _label_names_file(n.get("label"), sf):
            idx.setdefault(_norm(sf), n["id"])
        elif n.get("source_location") in (None, "", "null"):
            fallback.setdefault(_norm(sf), n["id"])
    for k, v in fallback.items():
        idx.setdefault(k, v)
    return idx


def augment_graph(graph: dict, enc: Encoding, couplings: list[Coupling]) -> dict:
    """Return graph copy with additive co_changes_with edges. Stats in graph
    ``["meta"]["graphmine"]``: how many couplings mapped onto file nodes."""
    idx = file_node_index(graph)
    lab = enc.id_label
    ek = edge_key(graph)
    out = {**graph, "nodes": list(graph.get("nodes", [])),
           ek: list(graph.get(ek, []))}
    added = 0
    unmapped = 0
    for c in couplings:
        sa, sb = idx.get(_norm(lab[c.a])), idx.get(_norm(lab[c.b]))
        if not sa or not sb:
            unmapped += 1
            continue
        out[ek].append({
            "source": sa, "target": sb, "relation": "co_changes_with",
            "confidence": "STATISTICAL", "confidence_score": c.p_raw, "p_raw": c.p_raw,
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


def augment_cooccurrence(graph: dict, enc: Encoding, couplings: list[Coupling],
                         *, relation: str = "co_occurs_with") -> dict:
    """Additive ``co_occurs_with`` edges directly between ENTITY nodes.

    For the text encoder the coupled items *are* graph node ids (kept in
    ``enc.meta["id_node"]``), so no file-node mapping is needed. Same contract
    as ``augment_graph``: non-destructive, ``STATISTICAL`` tier, raw Fisher p as
    the score, provenance so graphweave's ``merge``/report can trace the source.
    """
    id_node = enc.meta.get("id_node", {})
    have = {n["id"] for n in graph.get("nodes", [])}
    ek = edge_key(graph)
    out = {**graph, "nodes": list(graph.get("nodes", [])),
           ek: list(graph.get(ek, []))}
    added = 0
    unmapped = 0
    for c in couplings:
        sa, sb = id_node.get(c.a), id_node.get(c.b)
        if sa not in have or sb not in have:
            unmapped += 1
            continue
        out[ek].append({
            "source": sa, "target": sb, "relation": relation,
            "confidence": "STATISTICAL", "confidence_score": c.p_raw, "p_raw": c.p_raw,
            "provenance": "graphmine:text_cooccur", "weight": 1.0,
        })
        added += 1
    meta = dict(out.get("meta", {}))
    meta["graphmine"] = {f"{relation}_added": added, "unmapped_couplings": unmapped,
                         "of_total": len(couplings)}
    out["meta"] = meta
    return out


def write_augmented_cooccurrence(graph_json_path: str, enc: Encoding,
                                 couplings: list[Coupling], out_path: str) -> dict:
    graph = json.loads(open(graph_json_path, encoding="utf-8").read())
    aug = augment_cooccurrence(graph, enc, couplings)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(aug, f)
    return aug["meta"]["graphmine"]
