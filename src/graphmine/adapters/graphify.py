"""graphify adapter (plug-in surface).

Future home of the integration that turns graphmine findings into graphify
artifacts: typed, filterable ``co_changes_with`` edges (a STATISTICAL confidence
tier carrying the p-value) merged into a graph.json, and/or a report section.
graphify would depend on graphmine optionally; graphmine never imports graphify.

Stubbed until the standalone co-change pipeline is validated on real repos.
"""
from __future__ import annotations

from ..postprocess import Coupling
from ..encoders.base import Encoding


def couplings_to_graphify_edges(enc: Encoding, couplings: list[Coupling]) -> list[dict]:
    """Render couplings as graphify-style edges (not yet wired into graphify)."""
    lab = enc.id_label
    return [
        {
            "source": lab[c.a], "target": lab[c.b],
            "relation": "co_changes_with", "confidence": "STATISTICAL",
            "confidence_score": c.p,  # Fisher p-value; smaller = stronger
        }
        for c in couplings
    ]
