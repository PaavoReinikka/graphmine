"""graphmine CLI: encode a corpus -> mine -> postprocess -> report."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from . import report as report_mod
from .mine import mine
from .postprocess import clusters, pairwise_couplings


def _emit(enc, q, l_max, t_type, alpha, out_dir, name):
    rules = mine(enc, q=q, l_max=l_max, t_type=t_type)
    couplings = pairwise_couplings(rules, enc, alpha=alpha)
    cls = clusters(couplings, enc)
    data = report_mod.to_dict(enc, couplings, cls)
    md = report_mod.to_markdown(enc, couplings, cls)
    os.makedirs(out_dir, exist_ok=True)
    report_mod.write_json(os.path.join(out_dir, f"{name}.json"), data)
    with open(os.path.join(out_dir, f"{name}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"\n[graphmine] wrote {out_dir}/{name}.json and {name}.md")


def main(argv=None):
    # The Markdown digest uses non-ASCII (⇔, ·); Windows consoles default to
    # cp1252 and would raise UnicodeEncodeError on print(). Force UTF-8 stdout.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(prog="graphmine")
    p.add_argument("--version", action="version", version=f"graphmine {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--q", type=int, default=200, help="top-K rules to mine")
    common.add_argument("--l-max", type=int, default=2, help="max rule length")
    common.add_argument("--t-type", type=int, default=1, help="1=pos 2=neg 3=both")
    common.add_argument("--alpha", type=float, default=1e-3, help="significance threshold")
    common.add_argument("--out", default="out", help="output directory")

    cc = sub.add_parser("cochange", parents=[common], help="git co-change mining")
    cc.add_argument("repo")
    cc.add_argument("--max-commit-files", type=int, default=40)
    cc.add_argument("--min-freq", type=int, default=3)

    cr = sub.add_parser("coref", parents=[common], help="graph co-reference mining")
    cr.add_argument("graph_json")

    args = p.parse_args(argv)

    if args.cmd == "cochange":
        from .encoders import git_cochange
        enc = git_cochange.encode(args.repo, max_commit_files=args.max_commit_files,
                                  min_freq=args.min_freq)
        _emit(enc, args.q, args.l_max, args.t_type, args.alpha, args.out, "cochange")
    elif args.cmd == "coref":
        from .encoders import graph_coref
        enc = graph_coref.encode(args.graph_json)
        _emit(enc, args.q, args.l_max, args.t_type, args.alpha, args.out, "coref")
    return 0


if __name__ == "__main__":
    sys.exit(main())
