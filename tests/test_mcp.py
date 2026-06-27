"""Tests for the MCP service logic (GraphmineService) — no `mcp` package needed."""
import json

from graphmine.mcp_server import GraphmineService


def _write_index(tmp_path):
    idx = {
        "meta": {"significance": {"policy": "raw", "alpha": 0.05, "threshold": 0.05,
                                  "m_eff": None, "spectrum": None}, "git_head": "abc"},
        "by_file": {
            "a/x.py": {"subsystem": "a", "cluster": 0, "couples_with": [
                {"file": "a/y.py", "p_raw": 1e-6, "cross_subsystem": False}]},
            "a/y.py": {"subsystem": "a", "cluster": 0, "couples_with": [
                {"file": "a/x.py", "p_raw": 1e-6, "cross_subsystem": False}]},
        },
        "clusters": [{"members": ["a/x.py", "a/y.py"], "subsystems": ["a"],
                      "best_p": 1e-6, "size": 2, "cross_subsystem": False}],
        "couplings": [{"a": "a/x.py", "b": "a/y.py", "p_raw": 1e-6, "cross_subsystem": False}],
    }
    p = tmp_path / "idx.json"
    p.write_text(json.dumps(idx), encoding="utf-8")
    return str(p)


def test_service_blast_radius(tmp_path):
    s = GraphmineService(index_path=_write_index(tmp_path))
    r = s.blast_radius(["a/x.py"])
    assert [i["file"] for i in r["impacted"]] == ["a/y.py"]
    assert r["unknown_seeds"] == []
    r2 = s.blast_radius(["nope.py"])
    assert r2["impacted"] == [] and r2["unknown_seeds"] == ["nope.py"]


def test_service_clusters_and_status(tmp_path):
    s = GraphmineService(index_path=_write_index(tmp_path))
    assert s.clusters()["clusters"][0]["size"] == 2
    st = s.status()
    assert st["n_couplings"] == 1 and st["n_files"] == 2 and st["n_clusters"] == 1
    assert st["stale"] is None          # no repo -> can't be stale


def test_service_refresh_without_repo_errors(tmp_path):
    s = GraphmineService(index_path=_write_index(tmp_path))
    assert "error" in s.refresh()


def test_service_missing_index_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        GraphmineService(index_path=str(tmp_path / "nope.json"))
