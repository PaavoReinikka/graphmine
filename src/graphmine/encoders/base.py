"""The encoding contract: a corpus becomes transactions + item metadata.

Every encoder turns some corpus (a git repo, a graph.json, a text corpus) into a
binary transactional dataset Kingfisher can mine. Items are integer ids; the
sidecar maps each id back to a human label and a *subsystem* (used by
postprocessing to rank cross-cutting relations above within-subsystem ones).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


def auto_subsystem_depth(paths, *, max_depth: int = 3, dominance: float = 0.6) -> int:
    """Pick the directory depth at which a repo's components live.

    Works on the *directory* prefixes of the item paths (filename dropped, matching
    ``_subsystem``). Descends depth 1..max_depth while one subsystem dominates;
    returns the shallowest depth where the largest subsystem holds <= ``dominance``
    of the items, and stops early once going deeper no longer reduces that dominance
    (a flat/monolithic dir won't split). Capped at ``max_depth``.

    Examples: top-level components (src/, tests/, docs/) -> 1; everything under
    src/ (src/console, src/database, ...) -> 2; a flat repo -> 1.
    """
    dirsets = [p.replace("\\", "/").split("/")[:-1] for p in paths]
    dirsets = [d for d in dirsets if d]                 # ignore root-level files
    if not dirsets:
        return 1
    best, prev_top = 1, 1.1
    for depth in range(1, max_depth + 1):
        subs = Counter("/".join(d[:depth]) for d in dirsets)
        top_share = max(subs.values()) / sum(subs.values())
        if top_share <= dominance:
            return depth                                # components are spread out here
        if top_share >= prev_top - 1e-9:
            return best                                 # deeper didn't reduce dominance
        prev_top, best = top_share, depth
    return best


@dataclass
class Encoding:
    #: one transaction per row; each a sorted list of item ids present
    transactions: list[list[int]]
    #: item id -> human-readable label
    id_label: dict[int, str]
    #: item id -> subsystem key (e.g. top-level dir); for cross-subsystem ranking
    id_subsystem: dict[int, str] = field(default_factory=dict)
    #: free-form provenance (encoder name, params, corpus) for the report header
    meta: dict = field(default_factory=dict)

    @property
    def n_items(self) -> int:
        return len(self.id_label)

    @property
    def n_transactions(self) -> int:
        return len(self.transactions)

    def subsystem(self, item_id: int) -> str:
        return self.id_subsystem.get(item_id, "?")
