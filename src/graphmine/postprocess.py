"""Turn raw rules into reviewable findings: dedupe, clique-collapse, rank.

1. **dedupe** — collapse symmetric pairwise rules (A=>B, B=>A) into one undirected
   coupling keyed by the best (smallest) raw p.
2. **filter** — keep couplings whose raw p <= alpha.
3. **clique-collapse** — community detection over the significant couplings, so a
   mutually-coupled family shows up as one cluster, not O(n^2) pairs.
4. **rank** — cross-subsystem couplings first (more surprising than within-dir).

graphmine deliberately applies NO multiple-testing correction. Kingfisher's
branch-and-bound prunes and never enumerates the full hypothesis space, so the
number of tests is not well-defined and any FWER/FDR denominator would be
guesswork. We report the raw Fisher p-values and threshold on them directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .encoders.base import Encoding
from .mine import Rule


@dataclass
class Coupling:
    a: int
    b: int
    p_raw: float
    cross_subsystem: bool


@dataclass
class Cluster:
    members: list[int]
    subsystems: list[str]
    best_p: float
    cross_subsystem: bool
    size: int = field(init=False)

    def __post_init__(self):
        self.size = len(self.members)


def pairwise_couplings(rules: list[Rule], enc: Encoding) -> list[Coupling]:
    """All symmetric single-item Fisher rules -> deduped undirected couplings.

    Only Fisher rules (which carry a p-value) are eligible; the smallest raw p of
    the two directions is kept.
    """
    best: dict[tuple[int, int], float] = {}
    for r in rules:
        if r.is_negative or len(r.antecedent) != 1 or r.p is None:
            continue
        a, b = r.antecedent[0], r.consequent
        key = (a, b) if a < b else (b, a)
        if key not in best or r.p < best[key]:
            best[key] = r.p
    return [
        Coupling(a=a, b=b, p_raw=p,
                 cross_subsystem=enc.subsystem(a) != enc.subsystem(b))
        for (a, b), p in best.items()
    ]


def significant(couplings: list[Coupling], *, alpha: float) -> list[Coupling]:
    """Keep couplings with raw p <= alpha; cross-subsystem first, then by p."""
    out = [c for c in couplings if c.p_raw <= alpha]
    out.sort(key=lambda c: (not c.cross_subsystem, c.p_raw))
    return out


def _build_cluster(members: set[int], couplings: list[Coupling], enc: Encoding) -> Cluster:
    ps = [c.p_raw for c in couplings if c.a in members and c.b in members]
    subs = sorted({enc.subsystem(m) for m in members})
    return Cluster(members=sorted(members), subsystems=subs,
                   best_p=min(ps) if ps else 1.0, cross_subsystem=len(subs) > 1)


def clusters(couplings: list[Coupling], enc: Encoding) -> list[Cluster]:
    """Group coupled files into clusters via weighted community detection.

    Naive connected components merge everything that is transitively linked into
    one blob (e.g. many module<->test pairs bridged by shared commits). Modularity
    community detection over the coupling graph — edges weighted by significance
    (``-log10(p)``) — keeps tightly-coupled families together and splits weak
    bridges, so clusters stay meaningful. Falls back to components if networkx is
    unavailable.
    """
    if not couplings:
        return []
    import math
    try:
        import networkx as nx
        from networkx.algorithms.community import greedy_modularity_communities
    except ImportError:
        return _components(couplings, enc)

    g = nx.Graph()
    for c in couplings:
        g.add_edge(c.a, c.b, weight=-math.log10(max(c.p_raw, 1e-300)))

    try:
        comms = greedy_modularity_communities(g, weight="weight")
    except Exception:
        return _components(couplings, enc)

    out = [_build_cluster(set(comm), couplings, enc) for comm in comms if len(comm) >= 2]
    out.sort(key=lambda cl: (not cl.cross_subsystem, -cl.size, cl.best_p))
    return out


def _components(couplings: list[Coupling], enc: Encoding) -> list[Cluster]:
    """Fallback: connected components (used when networkx is absent)."""
    parent: dict[int, int] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c in couplings:
        ra, rb = find(c.a), find(c.b)
        if ra != rb:
            parent[ra] = rb
    members: dict[int, set[int]] = {}
    for c in couplings:
        members.setdefault(find(c.a), set()).update((c.a, c.b))
    out = [_build_cluster(mem, couplings, enc) for mem in members.values()]
    out.sort(key=lambda cl: (not cl.cross_subsystem, -cl.size, cl.best_p))
    return out
