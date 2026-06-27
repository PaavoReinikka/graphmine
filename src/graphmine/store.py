"""Global per-repo cache for Indexes — keeps the user's project space clean.

By default graphmine writes nothing into the project; a built Index is cached
under ``$XDG_CACHE_HOME/graphmine`` (else ``~/.graphmine``), keyed by the corpus
path. The CLI's ``-o`` opt-in and this cache use the *same* Index schema, and the
MCP server uses this same module — so CLI and MCP never disagree on location or
format.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


def _cache_root() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) / "graphmine") if xdg else (Path.home() / ".graphmine")


def repo_key(corpus: str) -> str:
    """Stable per-corpus key: ``<name>-<8-hex of absolute path>`` (disambiguates
    same-named repos in different locations)."""
    p = Path(corpus).resolve()
    name = p.name or "corpus"
    digest = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:8]
    return f"{name}-{digest}"


def cache_dir(corpus: str) -> Path:
    return _cache_root() / repo_key(corpus)


def index_path(corpus: str, encoder: str) -> Path:
    return cache_dir(corpus) / f"{encoder}.json"


def git_head(repo: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                             capture_output=True, text=True)
        return out.stdout.strip() or None
    except Exception:
        return None


def save(index: dict, corpus: str, encoder: str) -> Path:
    d = cache_dir(corpus)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{encoder}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    return path


def load(path_or_corpus: str, encoder: str | None = None) -> dict | None:
    """Load an Index from an explicit file path, or from the cache for a corpus.

    If ``path_or_corpus`` is a file it is loaded directly; otherwise it is treated
    as a corpus path and the cached ``<encoder>.json`` is loaded (None if absent).
    """
    p = Path(path_or_corpus)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    if encoder:
        ip = index_path(path_or_corpus, encoder)
        if ip.is_file():
            return json.loads(ip.read_text(encoding="utf-8"))
    return None


def is_stale(index: dict, repo: str) -> bool:
    """True if the repo's current git HEAD differs from the Index's stored HEAD."""
    stored = (index.get("meta") or {}).get("git_head")
    current = git_head(repo)
    return bool(current and stored and current != stored)
