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
    freq_a: int = 0      # support (commits) of item a
    freq_b: int = 0      # support of item b
    freq_ab: int = 0     # co-occurrence of a and b


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
    co: dict[tuple[int, int], int] = {}
    support: dict[int, int] = {}
    for r in rules:
        if r.is_negative or len(r.antecedent) != 1 or r.p is None:
            continue
        a, b = r.antecedent[0], r.consequent
        support[a] = r.freq_x          # antecedent support
        support[b] = r.freq_a          # consequent support
        key = (a, b) if a < b else (b, a)
        co[key] = r.freq_xa            # same co-occurrence for either direction
        if key not in best or r.p < best[key]:
            best[key] = r.p
    return [
        Coupling(a=a, b=b, p_raw=p,
                 cross_subsystem=enc.subsystem(a) != enc.subsystem(b),
                 freq_a=support.get(a, 0), freq_b=support.get(b, 0),
                 freq_ab=co.get((a, b), 0))
        for (a, b), p in best.items()
    ]


def significant(couplings: list[Coupling], *, alpha: float) -> list[Coupling]:
    """Keep couplings with raw p <= alpha; cross-subsystem first, then by p."""
    out = [c for c in couplings if c.p_raw <= alpha]
    out.sort(key=lambda c: (not c.cross_subsystem, c.p_raw))
    return out


def by_file_index(couplings: list[Coupling], clusters: list[Cluster],
                  enc: Encoding) -> dict[str, dict]:
    """Per-file adjacency for O(1) "everything about file X" lookups (blast radius).

    ``label -> {subsystem, cluster, couples_with: [{file, p_raw, cross_subsystem}]}``
    where ``couples_with`` is sorted by p (strongest coupling first).
    """
    lab = enc.id_label
    item_cluster: dict[int, int] = {}
    for ci, cl in enumerate(clusters):
        for m in cl.members:
            item_cluster[m] = ci

    n = enc.n_transactions
    adj: dict[int, dict] = {}

    def node(i: int) -> dict:
        if i not in adj:
            adj[i] = {"subsystem": enc.subsystem(i),
                      "cluster": item_cluster.get(i), "couples_with": []}
        return adj[i]

    def entry(other_label, c, supp_seed, supp_other):
        # effect sizes from the seed's perspective: confidence = P(other | seed)
        conf = supp_seed and c.freq_ab / supp_seed or 0.0
        lift = (c.freq_ab * n / (supp_seed * supp_other)
                if supp_seed and supp_other and n else 0.0)
        lev = (c.freq_ab / n - (supp_seed / n) * (supp_other / n)) if n else 0.0
        return {"file": other_label, "p_raw": c.p_raw,
                "cross_subsystem": c.cross_subsystem, "confidence": round(conf, 4),
                "lift": round(lift, 3), "leverage": round(lev, 6)}

    for c in couplings:
        node(c.a)["couples_with"].append(entry(lab[c.b], c, c.freq_a, c.freq_b))
        node(c.b)["couples_with"].append(entry(lab[c.a], c, c.freq_b, c.freq_a))

    for e in adj.values():
        e["couples_with"].sort(key=lambda d: d["p_raw"])
    return {lab[i]: e for i, e in adj.items()}


def suggest_exclusions(couplings: list[Coupling], enc: Encoding, *,
                       min_share: float = 0.5) -> list[dict]:
    """Flag a subsystem that dominates the couplings (a batch-migrated clique).

    Dirs whose files are committed in big batches (DB schema, migrations, generated
    code) form a giant within-subsystem clique that drowns real structure. If the
    most-coupled subsystem accounts for >= ``min_share`` of *all* couplings, return
    it as a hint to ``--exclude``; otherwise return nothing.
    """
    if not couplings:
        return []
    from collections import Counter
    within: Counter = Counter()
    for c in couplings:
        sa, sb = enc.subsystem(c.a), enc.subsystem(c.b)
        if sa == sb and sa not in ("(root)", "?"):
            within[sa] += 1
    total = len(couplings)
    out = []
    for sub, cnt in within.most_common(1):
        share = cnt / total
        if share >= min_share:
            out.append({"subsystem": sub, "within_couplings": cnt,
                        "share": round(share, 3)})
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
