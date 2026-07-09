"""Tests for the text co-occurrence encoder + entity-graph augmentation."""
import json

import pytest

from graphmine import analyze
from graphmine.adapters.graphify import augment_cooccurrence
from graphmine.encoders import text_cooccur
from graphmine.postprocess import Coupling


def _write(tmp_path, graph):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph), encoding="utf-8")
    return str(p)


def _node(nid, *, typ="entity", doc=None, chunks=None, layer="base"):
    n = {"id": nid, "label": nid, "type": typ, "layer": layer,
         "source_file": doc, "confidence": "EXTRACTED"}
    if chunks is not None:
        n["chunks"] = chunks
    return n


def _chunked_graph():
    # alice+acme always share chunks; bob drifts alone; corp appears once.
    return {"nodes": [
        _node("alice", typ="person", doc="a.txt", chunks=["a:0", "a:1", "a:2"]),
        _node("acme", typ="org", doc="a.txt", chunks=["a:0", "a:1", "a:2"]),
        _node("bob", typ="person", doc="a.txt", chunks=["a:3", "a:4"]),
        _node("corp", typ="org", doc="a.txt", chunks=["a:4"]),
    ], "edges": []}


def test_chunk_unit_auto_selected_and_transactions(tmp_path):
    enc = text_cooccur.encode(_write(tmp_path, _chunked_graph()))
    assert enc.meta["unit"] == "chunk"
    assert enc.meta["units"] == 5
    # corp appears in 1 chunk < min_freq=2 -> dropped
    assert set(enc.id_label.values()) == {"alice", "acme", "bob"}
    # transactions with >=2 kept items: the three alice+acme chunks and a:4 lost corp
    assert sorted(len(t) for t in enc.transactions) == [2, 2, 2]
    # single doc -> subsystems are entity types
    assert enc.meta["subsystem_kind"] == "type"
    assert set(enc.id_subsystem.values()) == {"person", "org"}


def test_sentence_unit_fallback_from_edges(tmp_path):
    g = {"nodes": [_node("a", doc="d.txt"), _node("b", doc="d.txt"),
                   _node("c", doc="d.txt")],
         "edges": [
             {"source": "a", "target": "b", "relation": "r", "sent_index": 0},
             {"source": "a", "target": "b", "relation": "r", "sent_index": 1},
             {"source": "b", "target": "c", "relation": "r", "sent_index": 2},
             {"source": "a", "target": "c", "relation": "r", "sent_index": 3},
         ]}
    # a/b/c each appear in >60% of the 4 sentences; lift the ubiquity cap since
    # this test is about the sentence fallback, not the frequency filter
    enc = text_cooccur.encode(_write(tmp_path, g), max_freq_frac=1.0)
    assert enc.meta["unit"] == "sentence"
    assert enc.n_transactions == 4 and enc.n_items == 3


def test_doc_unit_multi_doc_subsystem_is_doc(tmp_path):
    g = {"nodes": [
        _node("a", doc="x.txt", chunks=None), _node("b", doc="x.txt"),
        _node("a2", doc="y.txt"), _node("b2", doc="y.txt")],
        "edges": []}
    # no chunks, no sent_index -> only doc membership; but every entity is in
    # exactly 1 doc < min_freq -> relax min_freq to test the doc path itself
    enc = text_cooccur.encode(_write(tmp_path, g), unit="doc",
                              min_freq=1, max_freq_frac=1.0)
    assert enc.meta["unit"] == "doc" and enc.n_transactions == 2
    assert enc.meta["subsystem_kind"] == "doc"
    assert set(enc.id_subsystem.values()) == {"x.txt", "y.txt"}


def test_max_freq_frac_drops_ubiquitous_entity(tmp_path):
    g = _chunked_graph()
    g["nodes"].append(_node("the_firm", doc="a.txt",
                            chunks=["a:0", "a:1", "a:2", "a:3", "a:4"]))
    enc = text_cooccur.encode(_write(tmp_path, g))   # in 5/5 chunks > 0.6
    assert "the_firm" not in set(enc.id_label.values())


def test_concept_layer_lifts_membership_through_instance_of(tmp_path):
    g = _chunked_graph()
    g["nodes"] += [_node("people", layer="concept"), _node("companies", layer="concept")]
    g["edges"] += [
        {"source": "alice", "target": "people", "relation": "instance_of"},
        {"source": "bob", "target": "people", "relation": "instance_of"},
        {"source": "acme", "target": "companies", "relation": "instance_of"},
    ]
    enc = text_cooccur.encode(_write(tmp_path, g), layer="concept",
                              min_freq=1, max_freq_frac=1.0)
    assert set(enc.id_label.values()) == {"people", "companies"}
    # people+companies co-occur in the 3 alice/acme chunks
    both = [t for t in enc.transactions if len(t) == 2]
    assert len(both) == 3


def test_auto_without_membership_raises(tmp_path):
    g = {"nodes": [_node("a"), _node("b")], "edges": []}
    with pytest.raises(ValueError, match="no unit membership"):
        text_cooccur.encode(_write(tmp_path, g))


def test_end_to_end_mining_and_augment(tmp_path):
    # a strong alice-acme signal against background pairs (mirrors test_analyze)
    chunks_ab = [f"c:{i}" for i in range(6)]
    others = [f"o:{i}" for i in range(10)]
    g = {"nodes": [
        _node("alice", typ="person", doc="a.txt", chunks=chunks_ab),
        _node("acme", typ="org", doc="a.txt", chunks=chunks_ab),
        _node("p", doc="a.txt", chunks=others[:4]),
        _node("q", doc="a.txt", chunks=others[2:8]),
        _node("r", doc="a.txt", chunks=others[5:10]),
    ], "edges": [], "meta": {"generator": "graphweave"}}
    path = _write(tmp_path, g)
    enc = text_cooccur.encode(path)
    an = analyze.build(enc, policy="raw", alpha=0.05)
    lab = enc.id_label
    pairs = {frozenset((lab[c.a], lab[c.b])) for c in an.couplings}
    assert frozenset(("alice", "acme")) in pairs

    aug = augment_cooccurrence(json.loads(open(path, encoding="utf-8").read()),
                               enc, an.couplings)
    added = [e for e in aug["edges"] if e["relation"] == "co_occurs_with"]
    assert aug["meta"]["graphmine"]["co_occurs_with_added"] == len(added) > 0
    assert {e["source"] for e in added} | {e["target"] for e in added} <= \
        {n["id"] for n in g["nodes"]}
    for e in added:
        assert e["confidence"] == "STATISTICAL" and 0 <= e["p_raw"] <= 0.05
        assert e["provenance"] == "graphmine:text_cooccur"
    # non-destructive: original (empty) edge list untouched in the source graph
    assert g["edges"] == []


def test_augment_skips_unmapped_items():
    enc_meta = {"id_node": {0: "alice", 1: "ghost"}}
    from graphmine.encoders.base import Encoding
    enc = Encoding(transactions=[], id_label={0: "alice", 1: "ghost"},
                   meta=enc_meta)
    graph = {"nodes": [{"id": "alice"}], "edges": []}
    aug = augment_cooccurrence(graph, enc, [Coupling(a=0, b=1, p_raw=0.01,
                                                     cross_subsystem=True)])
    assert aug["meta"]["graphmine"]["co_occurs_with_added"] == 0
    assert aug["meta"]["graphmine"]["unmapped_couplings"] == 1
