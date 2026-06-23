"""Turn raw rules into reviewable findings: dedupe, correct, clique-collapse, rank.

1. **dedupe** — collapse symmetric pairwise rules (A=>B, B=>A) into one undirected
   coupling keyed by the best (smallest) raw p.
2. **correct** — apply multiple-testing correction over the pairwise family (see
   ``correct.py``); Fisher only (other measures have no p-value).
3. **filter** — keep couplings whose corrected p <= alpha.
4. **clique-collapse** — connected components over the significant couplings, so a
   mutually-coupled family shows up as one cluster, not O(n^2) pairs.
5. **rank** — cross-subsystem couplings first (more surprising than within-dir).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import correct as _correct
from .encoders.base import Encoding
from .mine import Rule


@dataclass
class Coupling:
    a: int
    b: int
    p_raw: float
    cross_subsystem: bool
    p_adj: float = None  # set by apply_correction


@dataclass
class Cluster:
    members: list[int]
    subsystems: list[str]
    best_p_adj: float
    cross_subsystem: bool
    size: int = field(init=False)

    def __post_init__(self):
        self.size = len(self.members)


def pairwise_couplings(rules: list[Rule], enc: Encoding) -> list[Coupling]:
    """All symmetric single-item Fisher rules -> deduped undirected couplings.

    No alpha filtering here — correction happens next. Only Fisher rules (which
    carry a p-value) are eligible.
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


def apply_correction(couplings: list[Coupling], enc: Encoding, *, method: str) -> None:
    """Set ``p_adj`` on each coupling (in place) using the chosen correction."""
    m = _correct.pairwise_family_size(enc.n_items)
    adj = _correct.adjust([c.p_raw for c in couplings], m, method)
    for c, a in zip(couplings, adj):
        c.p_adj = a


def significant(couplings: list[Coupling], *, alpha: float) -> list[Coupling]:
    out = [c for c in couplings if (c.p_adj if c.p_adj is not None else c.p_raw) <= alpha]
    out.sort(key=lambda c: (not c.cross_subsystem, c.p_adj))  # cross-subsystem, then q
    return out


def _build_cluster(members: set[int], couplings: list[Coupling], enc: Encoding) -> Cluster:
    qs = [(c.p_adj if c.p_adj is not None else c.p_raw)
          for c in couplings if c.a in members and c.b in members]
    subs = sorted({enc.subsystem(m) for m in members})
    return Cluster(members=sorted(members), subsystems=subs,
                   best_p_adj=min(qs) if qs else 1.0, cross_subsystem=len(subs) > 1)


def clusters(couplings: list[Coupling], enc: Encoding) -> list[Cluster]:
    """Group coupled files into clusters via weighted community detection.

    Naive connected components merge everything that is transitively linked into
    one blob (e.g. many module<->test pairs bridged by shared commits). Modularity
    community detection over the coupling graph — edges weighted by significance
    (``-log10(q)``) — keeps tightly-coupled families together and splits weak
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
        q = c.p_adj if c.p_adj is not None else c.p_raw
        g.add_edge(c.a, c.b, weight=-math.log10(max(q, 1e-300)))

    try:
        comms = greedy_modularity_communities(g, weight="weight")
    except Exception:
        return _components(couplings, enc)

    out = [_build_cluster(set(comm), couplings, enc) for comm in comms if len(comm) >= 2]
    out.sort(key=lambda cl: (not cl.cross_subsystem, -cl.size, cl.best_p_adj))
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
    out.sort(key=lambda cl: (not cl.cross_subsystem, -cl.size, cl.best_p_adj))
    return out
