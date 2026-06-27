"""MCP server exposing graphmine's blast-radius over a repo's co-change index.

The index is held **in memory** (built on startup, or loaded from the warm-start
cache) and served to an AI agent over MCP. It is the same Index schema and the
same build pipeline (`analyze.build`) the CLI uses, so an agent and a human can
share one cache without format drift.

Design: ``GraphmineService`` is plain, testable Python (the index state + the four
operations). ``build_mcp`` is a thin FastMCP wrapper over it, so the ``mcp``
package is only needed to actually *run* the server, not to test the logic.
"""
from __future__ import annotations

from . import analyze, query, store
from .encoders import git_cochange, graph_coref


class GraphmineService:
    """Holds an in-memory Index and answers blast-radius / cluster / status queries."""

    def __init__(self, *, repo: str | None = None, index_path: str | None = None,
                 encoder: str = "cochange", use_cache: bool = True,
                 build_kwargs: dict | None = None):
        self.repo = repo
        self.index_path = index_path
        self.encoder = encoder
        self.use_cache = use_cache
        self.build_kwargs = build_kwargs or {}
        self.index = self._load_initial()

    # --- index lifecycle ---------------------------------------------------
    def _build(self) -> dict:
        if not self.repo:
            raise ValueError("cannot build an index without a repo")
        bk = self.build_kwargs
        if self.encoder == "cochange":
            enc = git_cochange.encode(
                self.repo, min_freq=bk.get("min_freq", 3),
                max_commit_files=bk.get("max_commit_files", 40),
                subsystem_depth=bk.get("subsystem_depth", 1),
                exclude=tuple(bk.get("exclude", ())))
        else:
            enc = graph_coref.encode(self.repo,
                                     subsystem_depth=bk.get("subsystem_depth", 1))
        an = analyze.build(enc, policy=bk.get("policy", "raw"),
                           alpha=bk.get("alpha", 0.05),
                           git_head=store.git_head(self.repo))
        if self.use_cache:
            store.save(an.index, self.repo, self.encoder)
        return an.index

    def _load_initial(self) -> dict:
        if self.index_path:
            idx = store.load(self.index_path)
            if idx is None:
                raise ValueError(f"index not found: {self.index_path}")
            return idx
        if self.repo:
            idx = store.load(self.repo, self.encoder) if self.use_cache else None
            if idx is not None and not store.is_stale(idx, self.repo):
                return idx
            return self._build()
        raise ValueError("provide either repo or index_path")

    # --- operations (also the MCP tools) -----------------------------------
    def blast_radius(self, files: list[str], alpha: float | None = None,
                     depth: int = 1, limit: int | None = 50) -> dict:
        impacted = query.blast_radius(self.index, files, alpha=alpha,
                                      depth=depth, limit=limit)
        unknown = [f for f in files if not query.known_file(self.index, f)]
        return {"seeds": [f.replace("\\", "/") for f in files],
                "impacted": impacted, "unknown_seeds": unknown}

    def refresh(self) -> dict:
        if not self.repo:
            return {"error": "server was started from a static --index; cannot refresh"}
        self.index = self._build()
        m = self.index.get("meta", {})
        return {"refreshed": True, "couplings": len(self.index.get("couplings", [])),
                "git_head": m.get("git_head")}

    def clusters(self) -> dict:
        return {"clusters": self.index.get("clusters", [])}

    def status(self) -> dict:
        m = self.index.get("meta", {})
        return {
            "repo": self.repo, "encoder": self.encoder,
            "n_files": len(self.index.get("by_file", {})),
            "n_couplings": len(self.index.get("couplings", [])),
            "n_clusters": len(self.index.get("clusters", [])),
            "significance": m.get("significance"),
            "git_head": m.get("git_head"),
            "stale": store.is_stale(self.index, self.repo) if self.repo else None,
        }


def build_mcp(service: GraphmineService):
    """Wrap a GraphmineService as a FastMCP server (requires the `mcp` package)."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("graphmine")

    @mcp.tool()
    def blast_radius(files: list[str], alpha: float | None = None,
                     depth: int = 1, limit: int = 50) -> dict:
        """Files that have historically changed together with the given file(s).

        Use this to gauge the impact of editing a file ("what else usually moves
        with it?") or, given several files you are about to change, what else the
        change tends to pull in. Ranked by p (smaller = stronger coupling).

        Args:
            files: repo-relative path(s) to seed from (union of their radii).
            alpha: optional significance override; only *tightens* below the built
                threshold.
            depth: hops to expand (1 = direct co-change neighbours).
            limit: max results.
        """
        return service.blast_radius(files, alpha=alpha, depth=depth, limit=limit)

    @mcp.tool()
    def refresh() -> dict:
        """Re-mine the repository and refresh the in-memory index (use after new
        commits). No-op error if the server was started from a static index."""
        return service.refresh()

    @mcp.tool()
    def clusters() -> dict:
        """Co-change clusters — families of files that move together as a group."""
        return service.clusters()

    @mcp.tool()
    def status() -> dict:
        """Index metadata: corpus, significance policy, size, and whether the
        index is stale (repo HEAD moved since it was built)."""
        return service.status()

    return mcp


def serve(*, repo: str | None = None, index_path: str | None = None,
          encoder: str = "cochange", use_cache: bool = True, **build_kwargs) -> None:
    """Build the in-memory index and run the MCP server over stdio."""
    service = GraphmineService(repo=repo, index_path=index_path, encoder=encoder,
                               use_cache=use_cache, build_kwargs=build_kwargs)
    build_mcp(service).run()
