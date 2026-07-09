"""Encoding C — text co-occurrence. Transaction = a text unit (chunk, sentence,
or document) from a graphweave graph.json; items = the ENTITIES that occur in it.

This is the statistical layer of the graphweave pipeline: graphweave *generates*
entities/relations from text, this encoder + Kingfisher *annotate* them with
statistically significant co-occurrence (which pairs appear together far more
than their marginal frequencies predict). The couplings map straight back onto
the entity nodes, so the graphify adapter can append additive ``co_occurs_with``
edges (``STATISTICAL`` tier) without touching what graphweave asserted.

Membership sources, most granular first (``unit="auto"`` picks the best present):

* ``chunk``    — the ``chunks`` list graphweave's chunk-aware extraction
  (``extract_chunked`` / ``attach_text_features``) writes onto each node.
* ``sentence`` — reconstructed from the ``sent_index`` graphweave records on
  every deterministic edge (both endpoints occurred in that sentence).
* ``doc``      — each node's ``source_file``; only meaningful for multi-doc
  corpora (a transaction per document).

Subsystem (for cross-cutting ranking) is the source document when the corpus
has several — cross-DOC couplings are the surprising ones — otherwise the
entity type (person⇔org beats person⇔person).
"""
from __future__ import annotations

import json
from collections import defaultdict

from .base import Encoding

_UNITS = ("auto", "chunk", "sentence", "doc")
# lift's concept membership edge (graphweave: base --instance_of--> concept)
_CONCEPT_RELS = {"instance_of", "abstracts"}


def _node_docs(nodes: dict) -> set:
    return {n.get("source_file") for n in nodes.values() if n.get("source_file")}


def _chunk_membership(nodes: dict) -> dict[str, set[str]]:
    """unit key -> node ids, from the ``chunks`` attribute."""
    txn: dict[str, set[str]] = defaultdict(set)
    for nid, n in nodes.items():
        for cid in n.get("chunks") or ():
            txn[str(cid)].add(nid)
    return txn


def _sentence_membership(nodes: dict, edges: list) -> dict[tuple, set[str]]:
    """(doc, sent_index) -> node ids, from the sent_index on deterministic edges."""
    txn: dict[tuple, set[str]] = defaultdict(set)
    for e in edges:
        si = e.get("sent_index")
        if si is None:
            continue
        s, t = e.get("source"), e.get("target")
        if s not in nodes or t not in nodes:
            continue
        doc = nodes[s].get("source_file") or nodes[t].get("source_file")
        txn[(doc, si)].update((s, t))
    return txn


def _doc_membership(nodes: dict) -> dict[str, set[str]]:
    txn: dict[str, set[str]] = defaultdict(set)
    for nid, n in nodes.items():
        if n.get("source_file"):
            txn[n["source_file"]].add(nid)
    return txn


def _lift_to_concepts(txn: dict, nodes: dict, edges: list) -> dict:
    """Replace base members with the concept nodes that abstract them.

    graphweave's ``lift`` links ``base --instance_of--> concept``; a concept
    occurs in a unit iff one of its instances does. Base entities without a
    concept are dropped (the concept layer is a deliberate abstraction).
    """
    base_to_concept: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.get("relation") not in _CONCEPT_RELS:
            continue
        s, t = e.get("source"), e.get("target")
        # instance_of: base -> concept; abstracts: concept -> base
        b, c = (s, t) if e.get("relation") == "instance_of" else (t, s)
        if c in nodes and nodes[c].get("layer") == "concept":
            base_to_concept[b].add(c)
    out: dict = {}
    for key, members in txn.items():
        concepts = {c for m in members for c in base_to_concept.get(m, ())}
        if concepts:
            out[key] = concepts
    return out


def encode(graph_json: str, *, unit: str = "auto", layer: str = "base",
           min_freq: int = 2, max_freq_frac: float = 0.6) -> Encoding:
    """graphweave/graphify graph.json -> transactions of co-occurring entities.

    ``min_freq`` drops one-off entities (nothing to associate); ``max_freq_frac``
    drops ubiquitous ones (an entity in >60% of units couples with everything —
    the stopword of co-occurrence mining).
    """
    if unit not in _UNITS:
        raise ValueError(f"unit must be one of {_UNITS}")
    g = json.loads(open(graph_json, encoding="utf-8").read())
    nodes = {n["id"]: n for n in g.get("nodes", [])
             if n.get("layer", "base") == "base"}
    edges = g.get("edges", [])

    chosen = unit
    if unit == "auto":
        if len({cid for n in nodes.values() for cid in n.get("chunks") or ()}) >= 2:
            chosen = "chunk"
        elif len({e.get("sent_index") for e in edges
                  if e.get("sent_index") is not None}) >= 2:
            chosen = "sentence"
        elif len(_node_docs(nodes)) >= 2:
            chosen = "doc"
        else:
            raise ValueError(
                "graph carries no unit membership to mine: no 'chunks' on nodes "
                "(extract with graphweave --chunk), no 'sent_index' on edges, and "
                "fewer than 2 source documents")

    if chosen == "chunk":
        txn = _chunk_membership(nodes)
    elif chosen == "sentence":
        txn = _sentence_membership(nodes, edges)
    else:
        txn = _doc_membership(nodes)

    if layer == "concept":
        all_nodes = {n["id"]: n for n in g.get("nodes", [])}
        txn = _lift_to_concepts(txn, all_nodes, edges)
        nodes = {nid: n for nid, n in all_nodes.items() if n.get("layer") == "concept"}
    elif layer != "base":
        raise ValueError("layer must be 'base' or 'concept'")

    n = len(txn)
    counts: dict[str, int] = defaultdict(int)
    for items in txn.values():
        for it in items:
            counts[it] += 1
    keep = {it for it, c in counts.items()
            if c >= min_freq and c <= max_freq_frac * n}

    docs = _node_docs({nid: nodes[nid] for nid in keep if nid in nodes})
    subsystem_kind = "doc" if len(docs) >= 2 else "type"

    def _sub(nid: str) -> str:
        nd = nodes.get(nid, {})
        if subsystem_kind == "doc":
            return nd.get("source_file") or "?"
        return nd.get("type") or "entity"

    iid = {it: i for i, it in enumerate(sorted(keep))}
    id_label = {i: nodes[it].get("label", it) for it, i in iid.items()}
    id_subsystem = {i: _sub(it) for it, i in iid.items()}
    id_node = {i: it for it, i in iid.items()}

    transactions = []
    for items in txn.values():
        row = sorted(iid[it] for it in items if it in keep)
        if len(row) >= 2:
            transactions.append(row)

    return Encoding(transactions=transactions, id_label=id_label,
                    id_subsystem=id_subsystem,
                    meta={"encoder": "text_cooccur", "graph": graph_json,
                          "unit": chosen, "layer": layer, "units": n,
                          "subsystem_kind": subsystem_kind, "id_node": id_node})
