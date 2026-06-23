"""graphmine CLI: encode a corpus -> mine -> correct -> postprocess -> report."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from . import report as report_mod
from .correct import METHODS
from .mine import MEASURES, mine
from .postprocess import apply_correction, clusters, pairwise_couplings, significant


def _emit(enc, args, name):
    rules = mine(enc, q=args.q, l_max=args.l_max, t_type=args.t_type, measure=args.measure)
    couplings = pairwise_couplings(rules, enc)
    apply_correction(couplings, enc, method=args.correction)
    sig = significant(couplings, alpha=args.alpha)
    cls = clusters(sig, enc)
    data = report_mod.to_dict(enc, sig, cls, correction=args.correction, alpha=args.alpha)
    md = report_mod.to_markdown(enc, sig, cls, correction=args.correction, alpha=args.alpha)
    os.makedirs(args.out, exist_ok=True)
    report_mod.write_json(os.path.join(args.out, f"{name}.json"), data)
    with open(os.path.join(args.out, f"{name}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"\n[graphmine] wrote {args.out}/{name}.json and {name}.md")

    graph_path = getattr(args, "graphify_graph", None)
    if graph_path:
        from .adapters import graphify as gfy
        aug_path = os.path.join(args.out, f"{name}.graphify.json")
        stats = gfy.write_augmented(graph_path, enc, sig, aug_path)
        print(f"[graphmine] graphify: added {stats['co_changes_with_added']} "
              f"co_changes_with edges ({stats['unmapped_couplings']} of "
              f"{stats['of_total']} couplings had no matching file node) -> {aug_path}")


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
                        help="fisher (p-value; correctable) | chi2 | mi | leverage")
    common.add_argument("--correction", default="bh", choices=METHODS,
                        help="multiple-testing correction (Fisher only); default BH-FDR")
    common.add_argument("--alpha", type=float, default=0.05,
                        help="significance threshold on the corrected p (q-value)")
    common.add_argument("--subsystem-depth", type=int, default=1,
                        help="path depth that defines a 'subsystem' for cross-cutting ranking")
    common.add_argument("--out", default="out", help="output directory")

    cc = sub.add_parser("cochange", parents=[common], help="git co-change mining")
    cc.add_argument("repo")
    cc.add_argument("--max-commit-files", type=int, default=40)
    cc.add_argument("--min-freq", type=int, default=3)
    cc.add_argument("--include-deleted", action="store_true",
                    help="keep deleted / old-rename files (archaeology); default prunes "
                         "to currently-tracked files with rename-following")
    cc.add_argument("--graphify-graph", metavar="GRAPH_JSON",
                    help="also emit an augmented copy of this graphify graph.json with "
                         "additive co_changes_with edges (STATISTICAL tier, q as score)")

    cr = sub.add_parser("coref", parents=[common], help="graph co-reference mining")
    cr.add_argument("graph_json")

    args = p.parse_args(argv)
    if args.measure != "fisher" and args.correction != "none":
        print(f"[graphmine] note: --measure {args.measure} has no p-value; "
              f"correction/alpha do not apply (ranking by raw statistic).",
              file=sys.stderr)

    if args.cmd == "cochange":
        from .encoders import git_cochange
        enc = git_cochange.encode(args.repo, max_commit_files=args.max_commit_files,
                                  min_freq=args.min_freq, subsystem_depth=args.subsystem_depth,
                                  include_deleted=args.include_deleted)
        _emit(enc, args, "cochange")
    elif args.cmd == "coref":
        from .encoders import graph_coref
        enc = graph_coref.encode(args.graph_json, subsystem_depth=args.subsystem_depth)
        _emit(enc, args, "coref")
    return 0


if __name__ == "__main__":
    sys.exit(main())
