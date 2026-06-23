"""Run Kingfisher over an Encoding and return rules in a plain, engine-agnostic form."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .encoders.base import Encoding


@dataclass
class Rule:
    antecedent: tuple[int, ...]   # item ids
    consequent: int               # item id
    is_negative: bool
    p: float                      # Fisher p-value


def mine(
    enc: Encoding,
    *,
    q: int = 200,
    l_max: int = 2,
    t_type: int = 1,           # 1 = positive dependencies (the coupling case)
    m_threshold: float = 1.0,  # max p-value to return (1.0 = all top-q)
) -> list[Rule]:
    """Mine top-q significant rules. Thin wrapper over kingfisher_bnb so the rest
    of graphmine never imports the engine directly."""
    import kingfisher_bnb as kf

    if enc.n_transactions < 2 or enc.n_items < 2:
        return []
    raw = kf.find_rules_from_data(
        data=enc.transactions,
        k=enc.n_items - 1,
        q=q,
        l_max=l_max,
        t_type=t_type,
        m_threshold=m_threshold,
    )
    return [
        Rule(
            antecedent=tuple(r.antecedent),
            consequent=r.consequent,
            is_negative=bool(r.is_negative),
            p=math.exp(r.measure_value),
        )
        for r in raw
    ]
