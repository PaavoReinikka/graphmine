"""Unit tests for postprocessing — no Kingfisher needed (pure logic)."""
from graphmine.encoders.base import Encoding
from graphmine.mine import Rule
from graphmine.postprocess import clusters, pairwise_couplings


def _enc():
    # 5 items across 2 subsystems: a/* = {0,1,2}, b/* = {3,4}
    return Encoding(
        transactions=[],
        id_label={0: "a/x", 1: "a/y", 2: "a/z", 3: "b/p", 4: "b/q"},
        id_subsystem={0: "a", 1: "a", 2: "a", 3: "b", 4: "b"},
    )


def test_dedupe_symmetric_keeps_best_p():
    enc = _enc()
    rules = [
        Rule((0,), 1, False, 1e-5),
        Rule((1,), 0, False, 1e-4),   # symmetric dup, worse p -> dropped
    ]
    cps = pairwise_couplings(rules, enc, alpha=1e-3)
    assert len(cps) == 1
    assert cps[0].p == 1e-5


def test_alpha_filters_and_negatives_excluded():
    enc = _enc()
    rules = [
        Rule((0,), 1, False, 1e-2),   # above alpha -> out
        Rule((2,), 3, True, 1e-9),    # negative -> out
        Rule((0,), 2, False, 1e-6),   # in
    ]
    cps = pairwise_couplings(rules, enc, alpha=1e-3)
    assert len(cps) == 1 and {cps[0].a, cps[0].b} == {0, 2}


def test_cross_subsystem_flag_and_ranking():
    enc = _enc()
    rules = [
        Rule((0,), 1, False, 1e-4),   # within a
        Rule((0,), 3, False, 1e-5),   # cross a<->b
    ]
    cps = pairwise_couplings(rules, enc, alpha=1e-3)
    # cross-subsystem coupling ranked first
    assert cps[0].cross_subsystem and {cps[0].a, cps[0].b} == {0, 3}


def test_clique_collapse_into_components():
    enc = _enc()
    rules = [
        Rule((0,), 1, False, 1e-5),
        Rule((1,), 2, False, 1e-6),   # {0,1,2} one cluster
        Rule((3,), 4, False, 1e-7),   # {3,4} another
    ]
    cps = pairwise_couplings(rules, enc, alpha=1e-3)
    cls = clusters(cps, enc)
    sizes = sorted(c.size for c in cls)
    assert sizes == [2, 3]
