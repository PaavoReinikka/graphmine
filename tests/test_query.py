"""Tests for the pure query layer (blast_radius, m_eff_at, thresholds)."""
from graphmine import query


def _index(policy="raw", threshold=0.05, m_eff=None, spectrum=None):
    sig = {"policy": policy, "alpha": 0.05, "threshold": threshold,
           "m_eff": m_eff, "spectrum": spectrum}
    return {
        "meta": {"significance": sig},
        "by_file": {
            "a/x.py": {"subsystem": "a", "cluster": 0, "couples_with": [
                {"file": "a/y.py", "p_raw": 1e-6, "cross_subsystem": False},
                {"file": "b/z.py", "p_raw": 1e-3, "cross_subsystem": True}]},
            "a/y.py": {"subsystem": "a", "cluster": 0, "couples_with": [
                {"file": "a/x.py", "p_raw": 1e-6, "cross_subsystem": False}]},
            "b/z.py": {"subsystem": "b", "cluster": 1, "couples_with": [
                {"file": "a/x.py", "p_raw": 1e-3, "cross_subsystem": True},
                {"file": "b/w.py", "p_raw": 1e-4, "cross_subsystem": False}]},
            "b/w.py": {"subsystem": "b", "cluster": 1, "couples_with": [
                {"file": "b/z.py", "p_raw": 1e-4, "cross_subsystem": False}]},
        },
        "clusters": [], "couplings": [],
    }


def test_blast_radius_direct_ranked_by_p():
    res = query.blast_radius(_index(), ["a/x.py"])
    assert [r["file"] for r in res] == ["a/y.py", "b/z.py"]   # sorted by p
    assert all(r["hops"] == 1 for r in res)
    assert res[1]["cross_subsystem"] is True


def test_blast_radius_alpha_only_tightens():
    res = query.blast_radius(_index(), ["a/x.py"], alpha=1e-4)
    assert [r["file"] for r in res] == ["a/y.py"]            # b/z.py (1e-3) dropped


def test_blast_radius_depth_expands_transitively():
    res = query.blast_radius(_index(), ["a/x.py"], depth=2)
    hops = {r["file"]: r["hops"] for r in res}
    assert hops == {"a/y.py": 1, "b/z.py": 1, "b/w.py": 2}


def test_blast_radius_multi_seed_union_keeps_best_p():
    res = query.blast_radius(_index(), ["a/x.py", "b/w.py"])
    by = {r["file"]: r for r in res}
    assert "a/y.py" in by and "b/z.py" in by      # union of both radii
    assert by["b/z.py"]["p_raw"] == 1e-4          # min over the two seeds' edges


def test_blast_radius_normalizes_backslashes():
    res = query.blast_radius(_index(), ["a\\x.py"])
    assert [r["file"] for r in res] == ["a/y.py", "b/z.py"]


def test_known_file():
    idx = _index()
    assert query.known_file(idx, "a/x.py")
    assert query.known_file(idx, "a\\x.py")
    assert not query.known_file(idx, "nope.py")


def test_m_eff_at_matches_tarone():
    # [5,5,5] supports -> all 3 pairs testable -> m_eff=3
    assert query.m_eff_at([(1 / 252, 3)], 0.05) == 3
    # [1,5,5] -> only the (5,5) pair testable -> m_eff=1
    assert query.m_eff_at([(1 / 252, 1), (0.5, 2)], 0.05) == 1


def test_effective_threshold_tarone_tightens_with_alpha():
    idx = _index(policy="tarone", threshold=0.05 / 3, m_eff=3, spectrum=[(1 / 252, 3)])
    assert query.effective_threshold(idx, None) == 0.05 / 3          # as built
    assert query.effective_threshold(idx, 0.05) == 0.05 / 3          # same alpha
    assert query.effective_threshold(idx, 0.01) < 0.05 / 3           # tighter alpha
