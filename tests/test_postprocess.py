"""Unit tests for postprocessing — no Kingfisher needed (pure logic)."""
from graphmine.encoders.base import Encoding
from graphmine.mine import Rule
from graphmine.postprocess import clusters, pairwise_couplings, significant


def _enc():
    # 5 items across 2 subsystems: a/* = {0,1,2}, b/* = {3,4}
    return Encoding(
        transactions=[],
        id_label={0: "a/x", 1: "a/y", 2: "a/z", 3: "b/p", 4: "b/q"},
        id_subsystem={0: "a", 1: "a", 2: "a", 3: "b", 4: "b"},
    )


def _fisher(ant, cons, p, neg=False):
    return Rule((ant,), cons, neg, 1, p, p)


def test_dedupe_keeps_best_p_and_only_fisher():
    enc = _enc()
    rules = [_fisher(0, 1, 1e-5), _fisher(1, 0, 1e-4),       # symmetric -> best kept
             _fisher(2, 3, 1e-9, neg=True),                  # negative -> dropped
             Rule((4,), 0, False, 4, 12.3, None)]            # non-fisher (p=None) -> dropped
    cps = pairwise_couplings(rules, enc)
    assert len(cps) == 1 and cps[0].p_raw == 1e-5


def test_significance_filters_on_raw_p():
    enc = _enc()
    rules = [_fisher(0, 3, 1e-4), _fisher(0, 1, 1e-2)]
    cps = pairwise_couplings(rules, enc)
    sig = significant(cps, alpha=1e-3)
    # 1e-4 survives the raw threshold; 1e-2 does not
    assert len(sig) == 1 and {sig[0].a, sig[0].b} == {0, 3}
    assert sig[0].cross_subsystem  # a<->b


def test_significant_sorts_cross_subsystem_first():
    enc = _enc()
    rules = [_fisher(0, 1, 1e-9),    # within subsystem a, very small p
             _fisher(0, 3, 1e-4)]    # cross subsystem, larger p
    sig = significant(pairwise_couplings(rules, enc), alpha=0.05)
    assert sig[0].cross_subsystem and {sig[0].a, sig[0].b} == {0, 3}


def test_clusters_collapse_components():
    enc = _enc()
    rules = [_fisher(0, 1, 1e-6), _fisher(1, 2, 1e-6), _fisher(3, 4, 1e-6)]
    cps = pairwise_couplings(rules, enc)
    cls = clusters(significant(cps, alpha=0.05), enc)
    assert sorted(c.size for c in cls) == [2, 3]
