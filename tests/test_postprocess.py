"""Unit tests for correction + postprocessing — no Kingfisher needed (pure logic)."""
import math

from graphmine.correct import adjust, pairwise_family_size
from graphmine.encoders.base import Encoding
from graphmine.mine import Rule
from graphmine.postprocess import (apply_correction, clusters, pairwise_couplings,
                                   significant)


def _enc():
    # 5 items across 2 subsystems: a/* = {0,1,2}, b/* = {3,4}
    return Encoding(
        transactions=[],
        id_label={0: "a/x", 1: "a/y", 2: "a/z", 3: "b/p", 4: "b/q"},
        id_subsystem={0: "a", 1: "a", 2: "a", 3: "b", 4: "b"},
    )


def _fisher(ant, cons, p, neg=False):
    return Rule((ant,), cons, neg, 1, p, p)


# --- correction math ---------------------------------------------------------

def test_bonferroni_scales_by_family_size():
    assert adjust([0.01], 10, "bonferroni") == [0.1]
    assert adjust([0.5], 10, "bonferroni") == [1.0]  # capped at 1


def test_none_is_passthrough():
    assert adjust([0.01, 0.2], 5, "none") == [0.01, 0.2]


def test_bh_is_between_raw_and_bonferroni():
    ps = [0.001, 0.002, 0.003]
    raw, bonf = ps, adjust(ps, 100, "bonferroni")
    bh = adjust(ps, 100, "bh")
    for r, b, bn in zip(raw, bh, bonf):
        assert r <= b <= bn + 1e-12


def test_by_more_conservative_than_bh():
    ps = [0.0001, 0.0002, 0.0005]
    bh = adjust(ps, 1000, "bh")
    by = adjust(ps, 1000, "by")
    assert all(y >= h - 1e-12 for y, h in zip(by, bh))


def test_family_size():
    assert pairwise_family_size(5) == 10  # C(5,2)


# --- postprocess pipeline ----------------------------------------------------

def test_dedupe_keeps_best_p_and_only_fisher():
    enc = _enc()
    rules = [_fisher(0, 1, 1e-5), _fisher(1, 0, 1e-4),       # symmetric -> best kept
             _fisher(2, 3, 1e-9, neg=True),                  # negative -> dropped
             Rule((4,), 0, False, 4, 12.3, None)]            # non-fisher (p=None) -> dropped
    cps = pairwise_couplings(rules, enc)
    assert len(cps) == 1 and cps[0].p_raw == 1e-5


def test_correction_and_significance_filter():
    enc = _enc()                          # n_items=5 -> family m=10
    rules = [_fisher(0, 3, 1e-4), _fisher(0, 1, 1e-2)]
    cps = pairwise_couplings(rules, enc)
    apply_correction(cps, enc, method="bonferroni")  # *10
    sig = significant(cps, alpha=0.05)
    # 1e-4*10=1e-3 survives; 1e-2*10=0.1 does not
    assert len(sig) == 1 and {sig[0].a, sig[0].b} == {0, 3}
    assert sig[0].cross_subsystem  # a<->b


def test_clusters_collapse_components():
    enc = _enc()
    rules = [_fisher(0, 1, 1e-6), _fisher(1, 2, 1e-6), _fisher(3, 4, 1e-6)]
    cps = pairwise_couplings(rules, enc)
    apply_correction(cps, enc, method="none")
    cls = clusters(significant(cps, alpha=0.05), enc)
    assert sorted(c.size for c in cls) == [2, 3]
