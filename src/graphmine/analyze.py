"""The one build pipeline: Encoding -> Index. Shared by the CLI and the MCP server.

`build()` is the single place that turns an Encoding into the queryable Index, so
both surfaces produce the exact same schema (mixing CLI and MCP is format-safe).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import postprocess as pp
from . import report
from .encoders.base import Encoding
from .mine import mine, resolve_significance


@dataclass
class Analysis:
    enc: Encoding
    couplings: list          # significant Coupling objects (for markdown / graphify)
    clusters: list
    significance: dict
    index: dict              # the canonical Index dict (what gets cached / served)


def build(enc: Encoding, *, q: int = 400, l_max: int = 2, t_type: int = 1,
          measure: str = "fisher", policy: str = "raw", alpha: float = 0.05,
          git_head: str | None = None) -> Analysis:
    sig = resolve_significance(enc, policy=policy, alpha=alpha, measure=measure)
    # Mine at the effective threshold so the BnB prunes to (already-)significant
    # rules: faster, and the returned top-q is significant by construction. Only
    # for Fisher (a raw-p cutoff); other measures keep the permissive default.
    m_threshold = sig["threshold"] if measure == "fisher" else None
    rules = mine(enc, q=q, l_max=l_max, t_type=t_type, measure=measure,
                 m_threshold=m_threshold)
    couplings = pp.pairwise_couplings(rules, enc)
    sig_couplings = pp.significant(couplings, alpha=sig["threshold"])
    clusters = pp.clusters(sig_couplings, enc)
    by_file = pp.by_file_index(sig_couplings, clusters, enc)
    index = report.to_dict(enc, sig_couplings, clusters,
                           by_file=by_file, significance=sig, git_head=git_head)
    index["meta"]["suggestions"] = pp.suggest_exclusions(sig_couplings, enc)
    return Analysis(enc, sig_couplings, clusters, sig, index)
