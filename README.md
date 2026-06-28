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
# filtering: --exclude SUBSTR (repeatable, e.g. --exclude src/database) --min-freq --max-commit-files
# tuning: --alpha --subsystem-depth (auto|N; default auto) --measure {fisher,chi2,mi,leverage; Fisher-only}
```

By default graphmine writes **nothing into your project** — a built index goes to a
global per-repo cache (`~/.graphmine/<repo>/`, honoring `$XDG_CACHE_HOME`). Pass
`-o DIR` to write the index + Markdown report into the project instead.

graphmine **auto-detects `--subsystem-depth`** (and prints what it chose; pass an
integer to override) and, when one directory dominates the co-change (a
batch-migrated clique like a DB schema), prints a hint to `--exclude` it.

### Blast radius (which files change with this one)

Mine once, then query a file's co-change neighbourhood — instant, straight from the
cached index (no re-mining):

```bash
graphmine blast-radius --repo /path/to/repo --file src/foo.py
graphmine blast-radius --repo /path/to/repo --changed a.py,b.py --depth 2 --json
graphmine blast-radius out/cochange.json --file src/foo.py      # or point at an index file
```

`--changed` unions several seeds ("I'm about to touch these"); `--depth N` expands
transitively; `--alpha` re-thresholds (tighter only); `--json` is for tools/agents.
With `--repo`, the cached index is built on first use and reused thereafter.

### MCP server (for AI agents)

Expose the index to an AI agent over MCP. The server serves the query layer
**in memory** (built on startup, warm-start cached), using the same Index schema
as the CLI — so an agent and a human share one cache:

```bash
pip install 'graphmine[mcp]'
graphmine mcp --repo /path/to/repo          # stdio server; in-memory + warm-start cache
graphmine mcp --index out/cochange.json     # or serve a prebuilt index (read-only)
```

Tools: `blast_radius(files, alpha?, depth?, limit?)`, `refresh()` (re-mine after
new commits), `clusters()`, `status()`. Build knobs mirror `cochange`
(`--significance`, `--alpha`, `--subsystem-depth`, `--exclude`, …); `--no-cache`
for pure in-memory.

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

## Companion Skill (for AI agents)

[`skills/graphmine/`](skills/graphmine/SKILL.md) is a Claude Code skill that teaches
an agent to drive graphmine — the build → blast-radius → refresh workflow, the
tuning heuristics (depth = component level, exclude batch-migrated dirs, when Tarone
matters), and the MCP setup. Install it:

```bash
cp -r skills/graphmine ~/.claude/skills/                 # user-wide
# or per-project:  cp -r skills/graphmine <project>/.claude/skills/
```

## Status

Early/experimental. Co-change is the validated path. The Kingfisher engine ships
as the prebuilt [`kingfisher-bnb`](https://pypi.org/project/kingfisher-bnb/) wheel
on PyPI, so a fresh `uv sync` (or `pip install`) needs no Rust toolchain.

## License

MIT — see [LICENSE](LICENSE).
