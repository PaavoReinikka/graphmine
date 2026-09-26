"""Unit test for the graphify adapter — additive, typed co_changes_with edges."""
from graphmine.adapters.graphify import augment_graph, file_node_index
from graphmine.encoders.base import Encoding
from graphmine.postprocess import Coupling


def _graph():
    return {
        "nodes": [
            {"id": "a_x", "label": "a/x.py", "source_file": "a/x.py", "source_location": None},
            {"id": "b_y", "label": "b/y.py", "source_file": "b/y.py", "source_location": None},
            {"id": "sym", "label": "foo", "source_file": "a/x.py", "source_location": "L3"},
        ],
        "edges": [{"source": "sym", "target": "a_x", "relation": "contains"}],
    }


def _enc():
    return Encoding(transactions=[], id_label={0: "a/x.py", 1: "b/y.py", 2: "c/z.py"},
                    id_subsystem={0: "a", 1: "b", 2: "c"})


def test_file_node_index_picks_file_nodes_only():
    idx = file_node_index(_graph())
    assert idx == {"a/x.py": "a_x", "b/y.py": "b_y"}  # the symbol node is excluded


def test_augment_is_additive_and_typed():
    g = _graph()
    n_nodes, n_edges = len(g["nodes"]), len(g["edges"])
    enc = _enc()
    couplings = [Coupling(a=0, b=1, p_raw=1e-9, cross_subsystem=True)]
    aug = augment_graph(g, enc, couplings)
    # original untouched; one edge added
    assert len(aug["nodes"]) == n_nodes and len(aug["edges"]) == n_edges + 1
    e = aug["edges"][-1]
    assert e["relation"] == "co_changes_with" and e["confidence"] == "STATISTICAL"
    assert e["source"] == "a_x" and e["target"] == "b_y" and e["confidence_score"] == 1e-9
    assert aug["meta"]["graphmine"]["co_changes_with_added"] == 1


def test_unmapped_coupling_is_counted_not_added():
    g = _graph()
    enc = _enc()
    # item 2 = c/z.py has no file node in the graph
    couplings = [Coupling(a=0, b=2, p_raw=1e-9, cross_subsystem=True)]
    aug = augment_graph(g, enc, couplings)
    assert aug["meta"]["graphmine"] == {"co_changes_with_added": 0,
                                        "unmapped_couplings": 1, "of_total": 1}


def _graph_v09():
    # graphify >= 0.9 graph.json: node-link "links", file nodes at L1 labelled by
    # file name (bare or directory-qualified), plus a location-less anchor node
    # that shares a file's source_file (e.g. a Terraform directory anchor).
    return {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "a_x", "label": "x.py", "source_file": "a/x.py", "source_location": "L1"},
            {"id": "b_y", "label": "b/y.py", "source_file": "b/y.py", "source_location": "L1"},
            {"id": "sym", "label": "foo", "source_file": "a/x.py", "source_location": "L3"},
            {"id": "anchor", "label": "module: a", "source_file": "a/x.py", "source_location": None},
        ],
        "links": [{"source": "sym", "target": "a_x", "relation": "contains"}],
    }


def test_file_node_index_graphify_v09_labels():
    assert file_node_index(_graph_v09()) == {"a/x.py": "a_x", "b/y.py": "b_y"}


def test_augment_appends_to_links_not_a_new_edges_key():
    g = _graph_v09()
    aug = augment_graph(g, _enc(), [Coupling(a=0, b=1, p_raw=1e-9, cross_subsystem=True)])
    assert "edges" not in aug
    assert len(aug["links"]) == 2 and aug["links"][-1]["relation"] == "co_changes_with"
    assert g["links"] == [{"source": "sym", "target": "a_x", "relation": "contains"}]
