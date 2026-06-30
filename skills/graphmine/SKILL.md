---
name: graphmine
description: >-
  Find a file's co-change "blast radius" — the other files that have historically
  changed together with it (its tests, docs, and coupled modules) — before editing,
  so related changes aren't missed. Also surfaces a repository's evolutionary
  coupling and clusters. Use when about to modify a file and you want to know what
  else to update, when assessing the impact/blast-radius of a change, or when
  exploring how a codebase's files move together. Drives the `graphmine` CLI/MCP
  (statistically significant git co-change mining via Fisher's exact test).
---

# graphmine — co-change blast radius

`graphmine` mines **statistically significant co-change** from a repo's git
history: which files change together far more than chance (Fisher's exact test,
no minimum support). A file's **blast radius** = the files that historically move
with it, ranked by p (smaller = stronger). Use it *before* editing to catch the
tests, docs, and coupled modules you'd otherwise miss.

## Setup (once)

```bash
uv tool install "git+https://github.com/PaavoReinikka/graphmine"   # or: pip install graphmine (once on PyPI)
#   add the MCP server:  uv tool install "graphmine[mcp] @ git+https://github.com/PaavoReinikka/graphmine"
```
The engine (`kingfisher-bnb`) ships prebuilt wheels from PyPI — **no Rust toolchain needed**.
graphmine writes **nothing into the project**: indexes cache in `~/.graphmine/<repo>/`.

## Core workflow

1. **Build** the index (once per repo; rebuild after new commits):
   ```bash
   graphmine cochange <repo> --significance tarone        # add -v for drill-in suggestions
   ```
2. **Query** a file's blast radius (instant, reads the cache):
   ```bash
   graphmine blast-radius --repo <repo> --file path/to/file.py
   graphmine blast-radius --repo <repo> --changed a.py,b.py --depth 2 --json
   graphmine blast-radius --repo <repo> --file path/to/file.py --rank-by confidence
   ```
3. **Refresh** after new commits: re-run step 1 (or the MCP `refresh()` tool).

## Choosing settings (learned from real repos)

- **`--subsystem-depth` is auto-detected** (graphmine prints the chosen depth; pass
  an integer to override). It picks the level where components live — top-level
  `src/`, `tests/`, `docs/` → depth 1 (Flask); everything under one dir
  (`src/console`, `src/database`, …) → depth 2 (a monorepo). It only affects the
  cross-subsystem *ranking* (`[cross]`), not the couplings themselves.
- **Batch-committed dirs (DB schema/migrations, generated code) drown real coupling.**
  Three lines of defense, in order: (1) `--max-commit-files` is **auto by default** — a
  commit-size knee drops mega/migration commits, which usually tames the clique on its
  own; (2) graphmine still **auto-flags** any dir that dominates the couplings ("92%
  within `src/database`; consider --exclude …"); (3) opt-in **`--auto-exclude`** drops
  a confidently-detected batch clique outright and reports what it dropped.
  ```bash
  graphmine cochange <repo>                          # auto knee usually handles it
  graphmine cochange <repo> --exclude src/database   # or drop a dir manually
  graphmine cochange <repo> --auto-exclude           # or auto-detect & drop a batch clique
  ```
  (On one real repo this distilled 209 couplings → ~25 meaningful ones.)
- **`--significance tarone`** (recommended): a valid, cheap multiple-testing
  correction (Tarone's effective number of tests) that also tightens the search →
  **faster** mining. Default is raw `p ≤ --alpha`. Tarone matters most once the
  dominant batch clique is removed.
- High-churn files (changed in >40% of commits) are auto-pruned — they'd couple
  with everything.

## Reading the output

- **p** — raw Fisher p-value; smaller = stronger / more surprising co-change.
- **confidence / lift** — effect sizes. confidence = P(neighbour changes | seed
  changes); use `--rank-by confidence` to order by *strength* ("how likely B moves
  with A") rather than *significance* (p). lift is symmetric (× above chance).
- **`[cross]`** — the coupling crosses a subsystem boundary (often the interesting,
  cross-cutting links).
- **clusters** — families of files that move together as a group.
- **depth>1** — transitive neighbours (`h2` = two hops out).

**Typical real signals:** a source file ↔ its test (`cli.py ↔ tests/test_cli.py`),
a source file ↔ its docs (`cli.py ↔ docs/cli.rst`), a model ↔ its service ↔ its
infrastructure client, a workflow ↔ its inline script, config ↔ its `.env.example`.

## MCP (for agent loops)

Serve the index to an agent so it can query blast radius during a task:
```bash
graphmine mcp --repo <repo>            # stdio; in-memory + warm-start cache
```
Tools: `blast_radius(files, alpha?, depth?, limit?)`, `refresh()`, `clusters()`,
`status()`. Same index/cache as the CLI, so CLI and MCP can be mixed freely.

## Caveats

- Couplings are **Fisher-only** (they need a p-value); `--measure chi2|mi|leverage`
  run the engine but emit no couplings.
- Needs **git history** — new or rarely-changed files have little signal.
- Co-change is **evolutionary coupling, not causation** — a strong heuristic for
  "what tends to move together," not proof of a code dependency.

## Quick examples

```bash
# Flask (components at top level -> depth 1)
graphmine cochange ~/flask --significance tarone
graphmine blast-radius --repo ~/flask --file src/flask/cli.py
#   -> tests/test_cli.py (p≈2e-50), docs/cli.rst, src/flask/debughelpers.py

# Monorepo under src/, noisy DB schema (components at depth 2)
graphmine cochange <repo> --exclude src/database --significance tarone --subsystem-depth 2
graphmine blast-radius --repo <repo> --file src/functions-utils/models/message.py
#   -> services/state_service.py, infrastructure/service_bus.py
```
