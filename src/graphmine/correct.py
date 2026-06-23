"""Multiple-testing correction over a family of raw p-values.

Kingfisher does no family-wise/FDR correction, so graphmine applies its own.
The family size ``m`` is the number of hypotheses in the search space — for
pairwise (l_max=2) mining that is ``C(n_items, 2)`` (all possible item pairs).
We only see the smallest p-values (Kingfisher returns the top-q), which is
exactly what BH/BY need: those are the ones near the rejection boundary, and
their global ranks equal their ranks within the returned set.

Methods:
* ``none``       — passthrough (raw p).
* ``bonferroni`` — FWER: p_adj = min(1, p*m). Harsh.
* ``bh``         — Benjamini-Hochberg FDR. Assumes independence/PRDS. Default.
* ``by``         — Benjamini-Yekutieli FDR. Valid under arbitrary dependence,
                   but conservative (BH * harmonic(m)).
"""
from __future__ import annotations

import math

METHODS = ("none", "bonferroni", "bh", "by")


def pairwise_family_size(n_items: int) -> int:
    return max(1, n_items * (n_items - 1) // 2)


def _harmonic(m: int) -> float:
    # exact for small m; asymptotic (ln m + gamma + 1/2m) for large m
    if m <= 1000:
        return sum(1.0 / k for k in range(1, m + 1))
    return math.log(m) + 0.5772156649 + 1.0 / (2 * m)


def adjust(ps: list[float], m: int, method: str) -> list[float]:
    """Return adjusted p-values aligned to ``ps`` (input order preserved)."""
    if method == "none" or not ps:
        return list(ps)
    if method == "bonferroni":
        return [min(1.0, p * m) for p in ps]

    # BH / BY: step-up over the returned p's (which are the smallest in the family)
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    factor = _harmonic(m) if method == "by" else 1.0
    adj = [1.0] * len(ps)
    running_min = 1.0
    for pos in range(len(order) - 1, -1, -1):
        idx = order[pos]
        rank = pos + 1                     # global rank (these are the smallest p's)
        val = ps[idx] * m * factor / rank
        running_min = min(running_min, val)
        adj[idx] = min(1.0, running_min)
    return adj
