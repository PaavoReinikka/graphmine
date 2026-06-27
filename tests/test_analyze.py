"""Tests for significance resolution and the shared build pipeline (uses kingfisher)."""
from graphmine import analyze
from graphmine.encoders.base import Encoding
from graphmine.mine import resolve_significance


def _enc_signal():
    # items 0,1 are rare but ALWAYS together (far above chance) -> a clear 0-1
    # coupling; 2/3/4 are background noise in other subsystems.
    txns = [[0, 1]] * 6 + [[2, 3]] * 4 + [[3, 4]] * 4 + [[2, 4]] * 2
    return Encoding(transactions=txns,
                    id_label={0: "a/x", 1: "a/y", 2: "b/p", 3: "b/q", 4: "b/r"},
                    id_subsystem={0: "a", 1: "a", 2: "b", 3: "b", 4: "b"})


def test_analyze_build_raw_finds_coupling():
    an = analyze.build(_enc_signal(), policy="raw", alpha=0.05)
    assert an.significance["policy"] == "raw"
    pairs = {frozenset((c["a"], c["b"])) for c in an.index["couplings"]}
    assert frozenset(("a/x", "a/y")) in pairs
    assert an.index["by_file"]                      # non-empty adjacency
    assert "a/x" in an.index["by_file"]


def test_analyze_build_tarone_sets_m_eff():
    an = analyze.build(_enc_signal(), policy="tarone", alpha=0.05)
    s = an.significance
    assert s["policy"] == "tarone" and s["m_eff"] >= 1
    assert abs(s["threshold"] - 0.05 / s["m_eff"]) < 1e-12
    assert s["spectrum"]                            # spectrum stored for offline re-query


def test_resolve_significance_fisher_gating():
    # tarone requested with a non-Fisher measure -> silently falls back to raw
    s = resolve_significance(_enc_signal(), policy="tarone", alpha=0.05, measure="chi2")
    assert s["policy"] == "raw" and s["threshold"] == 0.05


def test_tarone_m_eff_counts_multiple_testable():
    # two strong pairs -> several testable hypotheses -> m_eff > 1, tighter cutoff
    txns = [[0, 1]] * 8 + [[2, 3]] * 8 + [[0, 2]] + [[1, 3]]
    enc = Encoding(transactions=txns,
                   id_label={0: "a", 1: "b", 2: "c", 3: "d"},
                   id_subsystem={i: "x" for i in range(4)})
    s = resolve_significance(enc, policy="tarone", alpha=0.05)
    assert s["m_eff"] >= 2
    assert s["threshold"] < 0.05
