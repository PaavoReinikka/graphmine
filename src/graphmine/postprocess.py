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


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def clusters(couplings: list[Coupling], enc: Encoding) -> list[Cluster]:
    """Connected components over the (already significance-filtered) couplings."""
    uf = _UnionFind()
    for c in couplings:
        uf.union(c.a, c.b)
    members: dict[int, set[int]] = {}
    best: dict[int, float] = {}
    for c in couplings:
        root = uf.find(c.a)
        members.setdefault(root, set()).update((c.a, c.b))
        best[root] = min(best.get(root, 1.0), c.p_adj if c.p_adj is not None else c.p_raw)
    out = []
    for root, mem in members.items():
        subs = sorted({enc.subsystem(m) for m in mem})
        out.append(Cluster(members=sorted(mem), subsystems=subs,
                           best_p_adj=best[root], cross_subsystem=len(subs) > 1))
    out.sort(key=lambda cl: (not cl.cross_subsystem, -cl.size, cl.best_p_adj))
    return out
