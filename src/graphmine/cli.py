"""graphmine CLI: encode a corpus -> mine -> postprocess -> report."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from . import analyze
from . import report as report_mod
from . import store
from .mine import MEASURES


def _emit(enc, args, corpus, name):
    an = analyze.build(enc, q=args.q, l_max=args.l_max, t_type=args.t_type,
                       measure=args.measure, policy=args.significance, alpha=args.alpha,
                       git_head=store.git_head(corpus))
    md = report_mod.to_markdown(enc, an.couplings, an.clusters, significance=an.significance)
    print(md)

    if args.out:                                   # explicit in-project output
        os.makedirs(args.out, exist_ok=True)
        jpath = os.path.join(args.out, f"{name}.json")
        report_mod.write_json(jpath, an.index)
        with open(os.path.join(args.out, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(md)
        out_dir = args.out
        print(f"\n[graphmine] wrote {jpath} and {name}.md")
    else:                                          # default: global cache, project clean
        jpath = store.save(an.index, corpus, name)
        out_dir = str(store.cache_dir(corpus))
        print(f"\n[graphmine] cached index -> {jpath}  (use -o DIR to write in-project)")

    graph_path = getattr(args, "graphify_graph", None)
    if graph_path:
        from .adapters import graphify as gfy
        aug_path = os.path.join(out_dir, f"{name}.graphify.json")
        stats = gfy.write_augmented(graph_path, enc, an.couplings, aug_path)
        print(f"[graphmine] graphify: added {stats['co_changes_with_added']} "
              f"co_changes_with edges ({stats['unmapped_couplings']} of "
              f"{stats['of_total']} couplings had no matching file node) -> {aug_path}")


def _resolve_index(args):
    """Get an Index for `blast-radius`: explicit path, or the repo's cached one
    (built with defaults if absent; a stale cache warns but is still used)."""
    if args.index:
        idx = store.load(args.index)
        if idx is None:
            print(f"[graphmine] index not found: {args.index}", file=sys.stderr)
        return idx
    if args.repo:
        idx = store.load(args.repo, args.encoder)
        if idx is not None:
            if store.is_stale(idx, args.repo):
                print(f"[graphmine] note: cached index is stale (repo HEAD moved); "
                      f"refresh with `graphmine {args.encoder} {args.repo}`", file=sys.stderr)
            return idx
        if args.encoder != "cochange":
            print(f"[graphmine] no cached {args.encoder} index for {args.repo}; build it "
                  f"first (e.g. `graphmine coref <graph.json>`)", file=sys.stderr)
            return None
        print(f"[graphmine] no cached index for {args.repo}; building with defaults...",
              file=sys.stderr)
        from .encoders import git_cochange
        enc = git_cochange.encode(args.repo)
        an = analyze.build(enc, git_head=store.git_head(args.repo))
        store.save(an.index, args.repo, "cochange")
        return an.index
    print("[graphmine] provide an INDEX.json path or --repo", file=sys.stderr)
    return None


def main(argv=None):
    # Markdown digest uses non-ASCII (⇔, ·); force UTF-8 stdout on Windows cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(prog="graphmine")
    p.add_argument("--version", action="version", version=f"graphmine {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--q", type=int, default=400, help="top-K rules to mine")
    common.add_argument("--l-max", type=int, default=2, help="max rule length")
    common.add_argument("--t-type", type=int, default=1, choices=(1, 2, 3),
                        help="rule direction: 1=positive 2=negative 3=both")
    common.add_argument("--measure", default="fisher", choices=tuple(MEASURES),
                        help="fisher (p-value) | chi2 | mi | leverage")
    common.add_argument("--alpha", type=float, default=0.05,
                        help="significance threshold on the Fisher p (raw, or "
                             "alpha/m_eff with --significance tarone)")
    common.add_argument("--significance", choices=("raw", "tarone"), default="raw",
                        help="raw: p<=alpha (default) | tarone: Fisher-only corrected "
                             "cut p<=alpha/m_eff (also prunes the search -> faster)")
    common.add_argument("--subsystem-depth", type=int, default=1,
                        help="path depth that defines a 'subsystem' for cross-cutting ranking")
    common.add_argument("-o", "--out", default=None, metavar="DIR",
                        help="write index+report into DIR in the project; default is a "
                             "global cache (~/.graphmine/<repo>/), leaving the project clean")

    cc = sub.add_parser("cochange", parents=[common], help="git co-change mining")
    cc.add_argument("repo")
    cc.add_argument("--max-commit-files", type=int, default=40)
    cc.add_argument("--min-freq", type=int, default=3)
    cc.add_argument("--include-deleted", action="store_true",
                    help="keep deleted / old-rename files (archaeology); default prunes "
                         "to currently-tracked files with rename-following")
    cc.add_argument("--graphify-graph", metavar="GRAPH_JSON",
                    help="also emit an augmented copy of this graphify graph.json with "
                         "additive co_changes_with edges (STATISTICAL tier, raw p as score)")

    cr = sub.add_parser("coref", parents=[common], help="graph co-reference mining")
    cr.add_argument("graph_json")

    br = sub.add_parser("blast-radius",
                        help="files that typically change with a given file (query an index)")
    br.add_argument("index", nargs="?", metavar="INDEX.json",
                    help="path to an index JSON; or use --repo to load the cached one")
    br.add_argument("--repo", help="load the cached index for this repo (build with "
                                   "defaults if absent; warn if stale)")
    br.add_argument("--encoder", default="cochange", choices=("cochange", "coref"),
                    help="which cached index to use with --repo (default cochange)")
    br.add_argument("--file", help="seed file (repo-relative path)")
    br.add_argument("--changed", help="comma-separated seed files (union of their radii)")
    br.add_argument("--alpha", type=float, default=None,
                    help="re-threshold at this alpha (tightens only; default: as built)")
    br.add_argument("--depth", type=int, default=1, help="hops to expand (1 = direct)")
    br.add_argument("--limit", type=int, default=None, help="cap number of results")
    br.add_argument("--json", action="store_true", dest="as_json",
                    help="machine-readable JSON output")

    args = p.parse_args(argv)
    if getattr(args, "measure", "fisher") != "fisher":
        msg = (f"[graphmine] note: --measure {args.measure} has no p-value; "
               f"alpha/significance do not apply and no couplings are emitted (Fisher only).")
        if getattr(args, "significance", "raw") == "tarone":
            msg += " (--significance tarone ignored.)"
        print(msg, file=sys.stderr)

    if args.cmd == "cochange":
        from .encoders import git_cochange
        enc = git_cochange.encode(args.repo, max_commit_files=args.max_commit_files,
                                  min_freq=args.min_freq, subsystem_depth=args.subsystem_depth,
                                  include_deleted=args.include_deleted)
        _emit(enc, args, args.repo, "cochange")
    elif args.cmd == "coref":
        from .encoders import graph_coref
        enc = graph_coref.encode(args.graph_json, subsystem_depth=args.subsystem_depth)
        _emit(enc, args, args.graph_json, "coref")
    elif args.cmd == "blast-radius":
        from . import query
        idx = _resolve_index(args)
        if idx is None:
            return 1
        seeds = []
        if args.file:
            seeds.append(args.file)
        if args.changed:
            seeds += [s.strip() for s in args.changed.split(",") if s.strip()]
        if not seeds:
            print("[graphmine] provide --file PATH or --changed a,b,...", file=sys.stderr)
            return 1
        res = query.blast_radius(idx, seeds, alpha=args.alpha, depth=args.depth,
                                 limit=args.limit)
        if args.as_json:
            print(json.dumps({"seeds": [s.replace("\\", "/") for s in seeds],
                              "impacted": res}, indent=2))
        else:
            for s in seeds:
                if not query.known_file(idx, s):
                    print(f"[graphmine] note: '{s}' has no significant couplings "
                          f"(or is not an indexed file)", file=sys.stderr)
            print(f"Blast radius for {', '.join(seeds)} — {len(res)} impacted file(s):")
            for r in res:
                tag = "  [cross]" if r["cross_subsystem"] else ""
                hop = f"  h{r['hops']}" if args.depth > 1 else ""
                print(f"  p={r['p_raw']:.1e}{hop}{tag}  {r['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
