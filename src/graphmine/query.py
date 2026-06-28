"""Pure query functions over a built Index dict — the cheap "query many" half.

No git, no Kingfisher: everything here reads the Index produced by ``analyze.build``
(and cached by ``store``), so the same functions back the ``blast-radius`` CLI and
(later) the MCP server identically.
"""
from __future__ import annotations


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def m_eff_at(spectrum: list, alpha: float) -> int:
    """Tarone effective number of tests for ``alpha`` from a stored minimal-p
    spectrum ``[(min_p, count), ...]`` (ascending by min_p). Mirrors kingfisher's
    k* search so re-thresholding needs no native dependency."""
    total = sum(c for _, c in spectrum)
    if total == 0:
        return 1

    def count_le(thr: float) -> int:
        s = 0
        for mp, c in spectrum:
            if mp <= thr:
                s += c
            else:
                break
        return s

    lo, hi = 1, total
    while lo < hi:
        mid = (lo + hi) // 2
        if count_le(alpha / mid) <= mid:
            hi = mid
        else:
            lo = mid + 1
    return lo


def effective_threshold(index: dict, alpha: float | None) -> float:
    """Raw-p cutoff to apply at query time.

    With ``alpha=None`` use the Index's build threshold. Otherwise re-derive the
    cutoff for ``alpha`` (Tarone: ``alpha / m_eff_at(spectrum, alpha)``; raw:
    ``alpha``) — but never looser than the build threshold, since couplings beyond
    it were pruned away during mining (query alpha can only *tighten*).
    """
    sig = (index.get("meta") or {}).get("significance") or {}
    build_thr = sig.get("threshold", 0.05)
    if alpha is None:
        return build_thr
    if sig.get("policy") == "tarone" and sig.get("spectrum"):
        requested = alpha / m_eff_at(sig["spectrum"], alpha)
    else:
        requested = alpha
    return min(build_thr, requested)


def blast_radius(index: dict, files, *, alpha: float | None = None,
                 depth: int = 1, limit: int | None = None,
                 rank_by: str = "p") -> list[dict]:
    """Files that typically change with ``files`` (the seed), ranked by p.

    ``depth=1`` is the direct co-change neighbourhood; ``depth>1`` expands
    transitively (BFS), tagging each hit with its hop distance. Multiple seeds are
    unioned (keeping each impacted file's strongest coupling). Returns dicts:
    ``{file, p_raw, cross_subsystem, hops}`` sorted by (hops, p).
    """
    by_file = index.get("by_file", {})
    thr = effective_threshold(index, alpha)
    seeds = [_norm(f) for f in files]
    seen = set(seeds)
    out: list[dict] = []
    frontier = list(seeds)

    for hop in range(1, max(1, depth) + 1):
        cand: dict[str, dict] = {}
        for f in frontier:
            node = by_file.get(f)
            if not node:
                continue
            for w in node["couples_with"]:
                if w["p_raw"] > thr:
                    continue
                nb = w["file"]
                if nb in seen:
                    continue
                if nb not in cand or w["p_raw"] < cand[nb]["p_raw"]:
                    cand[nb] = {"file": nb, "p_raw": w["p_raw"],
                                "cross_subsystem": w["cross_subsystem"], "hops": hop,
                                "confidence": w.get("confidence"), "lift": w.get("lift")}
        if not cand:
            break
        for nb, rec in cand.items():
            seen.add(nb)
            out.append(rec)
        frontier = list(cand)

    _key = {
        "p": lambda r: (r["hops"], r["p_raw"]),
        "confidence": lambda r: (r["hops"], -(r.get("confidence") or 0.0)),
        "lift": lambda r: (r["hops"], -(r.get("lift") or 0.0)),
    }.get(rank_by, lambda r: (r["hops"], r["p_raw"]))
    out.sort(key=_key)
    return out[:limit] if limit else out


def known_file(index: dict, path: str) -> bool:
    """True if ``path`` is an item with at least one significant coupling."""
    return _norm(path) in index.get("by_file", {})
