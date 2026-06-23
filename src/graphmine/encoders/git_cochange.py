"""Encoding C — co-change. Transaction = a git commit; items = files changed.

Discovers "changes(A) => changes(B)" couplings: files that evolve together far
more than chance. These are often invisible to static structure (e.g. files
generated from a shared template, or a release-bump pair).
"""
from __future__ import annotations

import subprocess
from collections import defaultdict

from .base import Encoding

# Files that co-change mechanically and only add noise.
_DEFAULT_SKIP_EXTS = (".lock", ".sum", ".svg", ".png", ".jpg", ".jpeg", ".gif")
_DEFAULT_SKIP_SUBSTRINGS = (
    "node_modules/", ".venv/", "graphify-out/", "/dist/", "/build/", "/target/",
)


def _subsystem(path: str, depth: int = 1) -> str:
    """First ``depth`` path segments — the unit we measure cross-cutting against.

    depth=1 -> top-level dir (good for flat repos); depth=2 distinguishes e.g.
    ``src/logic-app`` from ``src/database`` in repos where everything lives under
    one ``src/``.
    """
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 1:
        return "(root)"
    return "/".join(parts[:depth])


def _iter_commit_filesets(repo: str):
    out = subprocess.run(
        ["git", "-C", repo, "log", "--no-merges", "--pretty=format:%H", "--name-only"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    files: list[str] = []
    started = False
    for line in out.splitlines():
        line = line.strip()
        if len(line) == 40 and " " not in line and line.isalnum():  # commit hash
            if started and files:
                yield files
            files, started = [], True
        elif line:
            files.append(line)
    if started and files:
        yield files


def encode(
    repo: str,
    *,
    min_commit_files: int = 2,
    max_commit_files: int = 40,
    min_freq: int = 3,
    max_freq_frac: float = 0.4,
    subsystem_depth: int = 1,
    skip_exts: tuple = _DEFAULT_SKIP_EXTS,
    skip_substrings: tuple = _DEFAULT_SKIP_SUBSTRINGS,
) -> Encoding:
    """Build a co-change Encoding from a git repo.

    * ``max_commit_files`` drops mass commits (merges, reformats) that couple
      everything spuriously; ``min_commit_files`` drops singletons.
    * ``min_freq`` / ``max_freq_frac`` prune files too rare to co-occur or so
      ubiquitous (a changelog) that they couple with everything.
    """
    def keep_file(f: str) -> bool:
        fl = f.lower()
        if any(fl.endswith(e) for e in skip_exts):
            return False
        return not any(s in fl for s in skip_substrings)

    commits: list[set[str]] = []
    for files in _iter_commit_filesets(repo):
        kept = {f for f in files if keep_file(f)}
        if min_commit_files <= len(kept) <= max_commit_files:
            commits.append(kept)

    freq: dict[str, int] = defaultdict(int)
    for c in commits:
        for f in c:
            freq[f] += 1
    n = len(commits)
    keep = {f for f, c in freq.items() if c >= min_freq and c <= max_freq_frac * n}

    fid = {f: i for i, f in enumerate(sorted(keep))}
    id_label = {i: f for f, i in fid.items()}
    id_subsystem = {i: _subsystem(f, subsystem_depth) for f, i in fid.items()}

    transactions = []
    for c in commits:
        row = sorted(fid[f] for f in c if f in keep)
        if len(row) >= 2:
            transactions.append(row)

    return Encoding(
        transactions=transactions,
        id_label=id_label,
        id_subsystem=id_subsystem,
        meta={
            "encoder": "git_cochange", "repo": repo, "commits_used": n,
            "max_commit_files": max_commit_files, "min_freq": min_freq,
            "max_freq_frac": max_freq_frac,
        },
    )
