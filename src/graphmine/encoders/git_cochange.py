"""Encoding C — co-change. Transaction = a git commit; items = files changed.

Discovers "changes(A) => changes(B)" couplings: files that evolve together far
more than chance. These are often invisible to static structure (e.g. files
generated from a shared template, or a release-bump pair).

By default the item universe is pruned to files that **currently exist** in the
repo, with **rename-following** so a renamed file keeps its full history under
its present name; truly-deleted files drop out (pass ``include_deleted`` to keep
them for historical/archaeology analysis).
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


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, encoding="utf-8").stdout


def _tracked_files(repo: str) -> set[str]:
    return {ln.strip() for ln in _git(repo, "ls-files").splitlines() if ln.strip()}


def _parse_log(repo: str):
    """Yield (changed_paths) per commit, and collect rename edges old->new.

    Uses ``--name-status -M`` so renames appear as ``R<score>\\told\\tnew``; the
    changed file for that commit is ``new``, and we record old->new to fold the
    old path's history into the current name later.
    """
    out = _git(repo, "log", "--no-merges", "-M", "--name-status", "--pretty=format:%H")
    renames: dict[str, str] = {}
    files: list[str] = []
    started = False
    for line in out.splitlines():
        s = line.rstrip("\n")
        if len(s) == 40 and "\t" not in s and " " not in s and s.isalnum():
            if started and files:
                yield files
            files, started = [], True
            continue
        if not s or "\t" not in s:
            continue
        parts = s.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:        # rename: old -> new
            old, new = parts[1], parts[2]
            renames[old] = new
            files.append(new)
        else:
            files.append(parts[-1])
    if started and files:
        yield files
    _parse_log.renames = renames  # type: ignore[attr-defined]


def _canonical_map(renames: dict[str, str]) -> dict[str, str]:
    """Follow rename chains so every historical path maps to its latest name."""
    def resolve(p: str) -> str:
        seen = set()
        while p in renames and p not in seen:
            seen.add(p)
            p = renames[p]
        return p
    return {old: resolve(old) for old in renames}


def encode(
    repo: str,
    *,
    min_commit_files: int = 2,
    max_commit_files: int = 40,
    min_freq: int = 3,
    max_freq_frac: float = 0.4,
    subsystem_depth: int = 1,
    include_deleted: bool = False,
    skip_exts: tuple = _DEFAULT_SKIP_EXTS,
    skip_substrings: tuple = _DEFAULT_SKIP_SUBSTRINGS,
) -> Encoding:
    """Build a co-change Encoding from a git repo.

    * ``max_commit_files`` drops mass commits (merges, reformats); ``min_commit_files``
      drops singletons.
    * ``min_freq`` / ``max_freq_frac`` prune files too rare to co-occur or so
      ubiquitous (a changelog) that they couple with everything.
    * by default items are restricted to currently-tracked files (rename-aware);
      ``include_deleted=True`` keeps deleted/old-name files for archaeology.
    """
    def keep_file(f: str) -> bool:
        fl = f.lower()
        if any(fl.endswith(e) for e in skip_exts):
            return False
        return not any(s in fl for s in skip_substrings)

    commit_filesets = list(_parse_log(repo))
    rename_map = _canonical_map(getattr(_parse_log, "renames", {}))
    tracked = _tracked_files(repo)

    def canon(f: str) -> str:
        return rename_map.get(f, f)

    commits: list[set[str]] = []
    for files in commit_filesets:
        mapped = {canon(f) for f in files if keep_file(f)}
        if not include_deleted:
            mapped = {f for f in mapped if f in tracked}
        if min_commit_files <= len(mapped) <= max_commit_files:
            commits.append(mapped)

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
            "include_deleted": include_deleted, "renames_followed": len(rename_map),
        },
    )
