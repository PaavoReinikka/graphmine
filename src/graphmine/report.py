"""Render findings as a JSON sidecar and a human-readable Markdown digest."""
from __future__ import annotations

import json

from .encoders.base import Encoding
from .postprocess import Cluster, Coupling


def to_dict(enc: Encoding, couplings: list[Coupling], clusters: list[Cluster]) -> dict:
    lab = enc.id_label
    return {
        "meta": {**enc.meta, "n_transactions": enc.n_transactions,
                 "n_items": enc.n_items},
        "clusters": [
            {"members": [lab[m] for m in cl.members], "subsystems": cl.subsystems,
             "best_p": cl.best_p, "size": cl.size,
             "cross_subsystem": cl.cross_subsystem}
            for cl in clusters
        ],
        "couplings": [
            {"a": lab[c.a], "b": lab[c.b], "p": c.p,
             "cross_subsystem": c.cross_subsystem}
            for c in couplings
        ],
    }


def write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def to_markdown(enc: Encoding, couplings: list[Coupling], clusters: list[Cluster],
                *, top_couplings: int = 25) -> str:
    lab = enc.id_label
    m = enc.meta
    lines = [
        f"# graphmine — {m.get('encoder', 'findings')}",
        "",
        f"- corpus: `{m.get('repo') or m.get('graph') or '?'}`",
        f"- transactions: {enc.n_transactions} · items: {enc.n_items}",
        f"- significant couplings: {len(couplings)} · clusters: {len(clusters)}",
        "",
        "## Co-change clusters (families that move together)",
        "",
    ]
    if not clusters:
        lines.append("_none under the significance threshold_")
    for i, cl in enumerate(clusters, 1):
        tag = "cross-subsystem" if cl.cross_subsystem else cl.subsystems[0]
        lines.append(f"### Cluster {i} · {cl.size} files · {tag} · best p={cl.best_p:.1e}")
        for mem in cl.members:
            lines.append(f"- `{lab[mem]}`")
        lines.append("")
    lines += ["## Top cross-subsystem couplings (most surprising)", ""]
    cross = [c for c in couplings if c.cross_subsystem][:top_couplings]
    if not cross:
        lines.append("_none — all significant couplings are within a single subsystem_")
    for c in cross:
        lines.append(f"- `{lab[c.a]}` ⇔ `{lab[c.b]}`  (p={c.p:.1e})")
    lines.append("")
    return "\n".join(lines)
