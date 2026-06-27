"""Tests for the global per-repo cache (store.py)."""
from graphmine import store


def test_repo_key_stable_and_distinct(tmp_path):
    a = tmp_path / "repoA"; a.mkdir()
    b = tmp_path / "repoB"; b.mkdir()
    assert store.repo_key(str(a)) == store.repo_key(str(a))   # stable
    assert store.repo_key(str(a)) != store.repo_key(str(b))   # path-disambiguated


def test_save_load_roundtrip_in_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))       # isolate from real ~/.graphmine
    repo = tmp_path / "proj"; repo.mkdir()
    idx = {"meta": {"git_head": "abc123"}, "by_file": {}, "couplings": []}
    path = store.save(idx, str(repo), "cochange")
    assert path.is_file() and str(tmp_path) in str(path)      # landed in the cache, not the project
    assert store.load(str(repo), "cochange") == idx           # load by corpus + encoder
    assert store.load(str(path)) == idx                       # load by explicit path


def test_is_stale_handles_non_git(tmp_path):
    # no git HEAD obtainable -> cannot tell -> not stale (never a false positive)
    assert store.is_stale({"meta": {"git_head": "abc"}}, str(tmp_path)) is False
