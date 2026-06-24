# graphmine

Mine **statistically significant relations** from code repositories and knowledge
graphs — powered by [Kingfisher](https://github.com/PaavoReinikka/BranchAndBound)
(top-K non-redundant dependency-rule mining via Fisher's exact test, branch-and-
bound, multiple-testing correction, no minimum support).

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
uv sync                                    # builds the Kingfisher bindings (needs cargo)
uv run graphmine cochange /path/to/repo    # → out/cochange.{json,md}
uv run graphmine coref graph.json          # → out/coref.{json,md}
# tuning: --q --l-max --t-type {1,2,3} --alpha --max-commit-files --min-freq
```

## Status

Early/experimental. Co-change is the validated path. Kingfisher is not yet on
PyPI, so it is wired as a local path source (`../BranchAndBound/kingfisher`) — to
build from a fresh clone you currently need that sibling checkout and a Rust
toolchain (`uv sync` runs maturin). This will move to a normal dependency once
Kingfisher publishes.

## License

MIT — see [LICENSE](LICENSE).
