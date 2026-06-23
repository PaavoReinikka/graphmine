"""The encoding contract: a corpus becomes transactions + item metadata.

Every encoder turns some corpus (a git repo, a graph.json, a text corpus) into a
binary transactional dataset Kingfisher can mine. Items are integer ids; the
sidecar maps each id back to a human label and a *subsystem* (used by
postprocessing to rank cross-cutting relations above within-subsystem ones).
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
