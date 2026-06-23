"""Turn raw rules into reviewable findings: dedupe, clique-collapse, rank.

Three moves, in order:
1. **dedupe** — collapse symmetric pairwise rules (A=>B and B=>A) into one
   undirected coupling keyed by the best (smallest) p-value.
2. **clique-collapse** — connected components over the significant couplings, so a
   family of mutually-coupled items (e.g. files generated from one template)
   shows up as a single *cluster* instead of O(n^2) redundant pairs.
3. **rank** — surface cross-subsystem relations first: a coupling spanning two
   different subsystems is more surprising than one within a single directory.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .encoders.base import Encoding
from .mine import Rule


@dataclass
class Coupling:
    a: int
    b: int
    p: float
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


def pairwise_couplings(rules: list[Rule], enc: Encoding, *, alpha: float) -> list[Coupling]:
    """Symmetric, single-item rules -> undirected couplings under significance alpha."""
    best: dict[tuple[int, int], float] = {}
    for r in rules:
        if r.is_negative or len(r.antecedent) != 1:
            continue
        if r.p > alpha:
            continue
        a, b = r.antecedent[0], r.consequent
        key = (a, b) if a < b else (b, a)
        if key not in best or r.p < best[key]:
            best[key] = r.p
    out = [
        Coupling(a=a, b=b, p=p,
                 cross_subsystem=enc.subsystem(a) != enc.subsystem(b))
        for (a, b), p in best.items()
    ]
    out.sort(key=lambda c: (not c.cross_subsystem, c.p))  # cross-subsystem first, then p
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
    """Connected components over the significant couplings."""
    uf = _UnionFind()
    for c in couplings:
        uf.union(c.a, c.b)
    groups: dict[int, list[int]] = {}
    pmap: dict[int, float] = {}
    for c in couplings:
        root = uf.find(c.a)
        groups.setdefault(root, [])
        pmap[root] = min(pmap.get(root, 1.0), c.p)
    member_of: dict[int, set[int]] = {}
    for c in couplings:
        root = uf.find(c.a)
        member_of.setdefault(root, set()).update((c.a, c.b))
    out = []
    for root, members in member_of.items():
        subs = sorted({enc.subsystem(m) for m in members})
        out.append(Cluster(members=sorted(members), subsystems=subs,
                            best_p=pmap[root], cross_subsystem=len(subs) > 1))
    # biggest, most-significant, cross-cutting clusters first
    out.sort(key=lambda cl: (not cl.cross_subsystem, -cl.size, cl.best_p))
    return out
