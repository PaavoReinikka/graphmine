# graphmine

Mine **statistically significant relations** from code repositories and knowledge
graphs — powered by [Kingfisher](https://github.com/PaavoReinikka/kingfisher-bnb)
(top-K non-redundant dependency-rule mining via Fisher's exact test, branch-and-
bound, no minimum support; raw p-values). By default graphmine reports these raw
Fisher p-values (a pruned top-K search has no well-defined number of tests); an
opt-in `--significance tarone` applies a valid, cheap correction — Tarone's
*effective* number of tests, counting only testable hypotheses — which also
tightens the search and speeds mining.

graphmine turns a corpus into a transactional dataset, mines significant rules,
then **dedupes, clique-collapses, and ranks cross-subsystem relations first**, and
writes an additive JSON sidecar + Markdown digest. It is a **standalone tool**;
[graphify](https://github.com/PaavoReinikka/graphify) is one optional consumer
(via `adapters/graphify.py`), not a dependency.

```
encoder (corpus → transactions+labels) → mine (Kingfisher) → postprocess → report
```

## Encoders

| Encoder | Transaction | Items | Finds |
|---|---|---|---|
| `cochange` | a git commit | files changed together | evolutionary coupling (often static-invisible) |
| `coref` | a file | cross-file symbols it references | static co-reference associations |
| *(planned)* `feature` | a node | one-hot node attributes | community/cluster characterization |
| *(planned)* `text` | a doc | normalized terms/concepts | doc term associations |

## Use

```bash
uv sync                                    # installs deps incl. the kingfisher-bnb wheel (no toolchain)
uv run graphmine cochange /path/to/repo    # caches the index in ~/.graphmine/<repo>/ (project stays clean)
uv run graphmine cochange /path/to/repo -o out/   # opt in to writing index+report into the project
uv run graphmine coref graph.json          # static co-reference mining
# significance: --significance raw (default) | tarone   (Fisher-only; also prunes -> faster)
# tuning: --measure {fisher,chi2,mi,leverage} --alpha --subsystem-depth
#         --max-commit-files --min-freq --include-deleted
```

By default graphmine writes **nothing into your project** — a built index goes to a
global per-repo cache (`~/.graphmine/<repo>/`, honoring `$XDG_CACHE_HOME`). Pass
`-o DIR` to write the index + Markdown report into the project instead.

### Plugging into graphify

Pass `--graphify-graph` to also emit a copy of a [graphify](https://github.com/PaavoReinikka/graphify)
`graph.json` with additive, typed `co_changes_with` edges (a `STATISTICAL`
confidence tier carrying the raw Fisher p-value); the original graph is left
untouched:

```bash
graphmine cochange /repo --graphify-graph graphify-out/graph.json --out graphify-out
```

graphify wraps this as `graphify cochange` when graphmine is on PATH (install via
`uv tool install ./graphmine`).

## Status

Early/experimental. Co-change is the validated path. The Kingfisher engine ships
as the prebuilt [`kingfisher-bnb`](https://pypi.org/project/kingfisher-bnb/) wheel
on PyPI, so a fresh `uv sync` (or `pip install`) needs no Rust toolchain.

## License

MIT — see [LICENSE](LICENSE).
