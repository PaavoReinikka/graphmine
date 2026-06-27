"""Run Kingfisher over an Encoding; return rules in an engine-agnostic form.

Kingfisher returns RAW, uncorrected scores (it controls false discovery only by
top-K + non-redundancy + a raw threshold — no family-wise/FDR correction). For
the Fisher measure that score is a p-value; graphmine reports it raw and does not
apply multiple-testing correction (a pruned top-K search has no well-defined
number of tests). For chi2/mi/leverage the score is a test statistic / effect
size, not a p-value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .encoders.base import Encoding

# name -> Kingfisher measure_type. 1/2 are Fisher (the p-value measures).
MEASURES = {"fisher": 1, "chi2": 3, "mi": 4, "leverage": 5}
_P_VALUE_MEASURES = {1, 2}


@dataclass
class Rule:
    antecedent: tuple[int, ...]
    consequent: int
    is_negative: bool
    measure_type: int
    score: float            # comparable score (Fisher: p; others: the statistic)
    p: float | None         # raw Fisher p-value, or None when the measure has no p


def mine(
    enc: Encoding,
    *,
    q: int = 200,
    l_max: int = 2,
    t_type: int = 1,            # rule direction: 1=positive 2=negative 3=both
    measure: str = "fisher",    # fisher | chi2 | mi | leverage
    m_threshold: float | None = None,
) -> list[Rule]:
    import kingfisher_bnb as kf

    if enc.n_transactions < 2 or enc.n_items < 2:
        return []
    mt = MEASURES[measure]
    is_p = mt in _P_VALUE_MEASURES
    # m_threshold is a RAW cutoff. Default to "accept all top-q": p<=1 for Fisher,
    # a permissive statistic bound otherwise.
    if m_threshold is None:
        m_threshold = 1.0 if is_p else 1e18

    raw = kf.find_rules_from_data(
        data=enc.transactions, k=enc.n_items - 1, q=q, l_max=l_max,
        t_type=t_type, m_threshold=m_threshold, measure_type=mt,
    )
    out = []
    for r in raw:
        if is_p:
            p = math.exp(r.measure_value)       # measure_value = ln(p)
            score = p
        else:
            p = None
            score = -r.measure_value            # stored negated so smaller=better
        out.append(Rule(tuple(r.antecedent), r.consequent, bool(r.is_negative),
                         mt, score, p))
    return out


def resolve_significance(enc: Encoding, *, policy: str = "raw", alpha: float = 0.05,
                         measure: str = "fisher") -> dict:
    """Resolve the significance policy into an effective raw-p threshold.

    * ``raw``    -> threshold = alpha.
    * ``tarone`` -> threshold = alpha / m_eff, where m_eff is Tarone's effective
      number of tests (Kingfisher's ``tarone()``, reusing its Fisher min-p bounds).
      Fisher-only: a non-Fisher measure (no p-value) silently falls back to raw.

    The returned ``threshold`` doubles as the mining ``m_threshold`` — a tighter
    cutoff prunes the branch-and-bound search harder, so Tarone mining is faster.
    The ``spectrum`` lets a consumer recompute m_eff for any alpha offline.
    """
    raw = {"policy": "raw", "alpha": alpha, "threshold": alpha,
           "m_eff": None, "spectrum": None}
    if policy != "tarone" or measure != "fisher":
        return raw
    if enc.n_transactions < 2 or enc.n_items < 2:
        return raw
    import kingfisher_bnb as kf

    res = kf.tarone(enc.transactions, enc.n_items - 1, alpha)
    return {"policy": "tarone", "alpha": alpha, "threshold": res.threshold,
            "m_eff": res.m_eff, "spectrum": list(res.spectrum)}
