# graphmine — methodology

How graphmine decides that two files "change together," how it scores and ranks
those relations, and how its automatic choices are made. This is the reference; the
[README](../README.md) covers usage and the [skill](../skills/graphmine/SKILL.md)
covers the agent workflow.

## 1. What it computes

graphmine mines **evolutionary coupling** from a repository's history: files that
change together far more often than chance. The unit of observation is a
**transaction**; the things that co-occur in it are **items**:

| Encoder | Transaction | Items |
|---|---|---|
| `cochange` | a git commit | the files changed in it (after pruning) |
| `coref` | a file | the cross-file symbols it references |

The rest of this document focuses on `cochange`. The output is a set of
**couplings** — undirected file pairs that co-occur significantly — plus
**clusters** (families that move together) and a per-file index for fast queries.

## 2. The pipeline

```
corpus → Encoding → mine (Kingfisher) → couplings → Index → query (blast-radius)
```

- **Encoding**: transactions (lists of item ids) + `id_label` (id → path) +
  `id_subsystem` (id → component) + provenance `meta`.
- **mine**: Kingfisher finds the top-K significant, non-redundant pairwise rules.
- **couplings**: symmetric Fisher rules deduped into undirected pairs, each carrying
  the contingency counts.
- **Index**: the queryable artifact (`couplings`, `by_file` adjacency, `clusters`,
  `meta`) — the same schema used by the CLI and the MCP server.

## 3. Significance — Fisher's exact test

For a pair (A, B), graphmine forms the 2×2 contingency table over all transactions
(A present/absent × B present/absent) and applies **Fisher's exact test**. The
result is a **p-value**: the probability, under the null hypothesis that A and B are
independent, of seeing a co-occurrence *this extreme or more*. Small p ⇒ the
co-change is surprising (unlikely to be coincidence).

Two deliberate choices:

- **No minimum support.** Kingfisher (Hämäläinen, ICDM 2010) discovers the top-K
  optimal dependency rules by branch-and-bound *without* a support threshold, so
  rare-but-deterministic couplings are not missed.
- **p is significance, not strength.** p is sensitive to sample size: two files that
  both change constantly can reach a tiny p even when their association is modest.

## 4. Strength — effect sizes

To answer "how strongly / how *actionably* are they coupled?" graphmine derives
effect sizes from the same contingency counts (`freq_a`, `freq_b`, `freq_ab`, n =
number of transactions):

- **confidence** = `P(B changes | A changes)` = `freq_ab / freq_a`. **Directional.**
  "If I touch A, B needs touching X% of the time." The most actionable for blast
  radius.
- **lift** = `P(A∧B) / (P(A)·P(B))` = `freq_ab·n / (freq_a·freq_b)` — how many times
  above chance (symmetric).
- **leverage** = `P(A∧B) − P(A)·P(B)` (symmetric).

`blast-radius --rank-by {p,confidence,lift}`: **p still gates** (the significance
cutoff decides which couplings survive); `--rank-by` only **reorders** the survivors.
Use `confidence` when you care about "what else will I have to change," `p` when you
care about "what is most surprising."

## 5. Multiple testing — why correction is off by default

Mining many pairs means many tests, so a naïve `p ≤ 0.05` over-reports. The usual fix
is a family-wise/FDR correction with denominator m (the number of tests). **But a
pruned top-K branch-and-bound search has no well-defined m** — it never enumerates the
full hypothesis space — so a Bonferroni/BH denominator like `C(n_items, 2)` is
guesswork and the resulting "corrected q-values" are misleading. graphmine therefore
reports **raw p** by default and thresholds on it directly.

**`--significance tarone`** (opt-in) is the principled correction:

- For a *discrete* test (Fisher on a 2×2 with fixed margins) each pair has a
  **minimum attainable p** given its supports. A pair too rare to ever reach the
  threshold is **untestable** and excluded from the count.
- Tarone's **effective number of tests** is `m_eff = min{ k : #(min-p ≤ α/k) ≤ k }`;
  reject when raw `p ≤ α/m_eff`. This controls the family-wise error rate validly,
  and `m_eff` is usually far smaller than `C(n_items, 2)`.
- **Bonus:** `α/m_eff` is a tighter raw-p cutoff, fed to the BnB as the mining
  threshold → harder pruning → *faster* mining.
- Correction is defined on p-values, so it is **Fisher-only**. (`m_eff` is always
  computed and stored in the index; only its *use* is opt-in.)

## 6. Automatic parameter selection

- **`--subsystem-depth` (auto).** A "subsystem" is the boundary a coupling crossing
  is considered *surprising* (cross-cutting). Auto-detection descends the directory
  tree while one top-level directory dominates the item paths, stopping at the level
  where components actually live (top-level `src/`,`tests/`,`docs/` → depth 1;
  everything under one `src/` → depth 2). It affects cross-subsystem *ranking* only —
  blast-radius itself is depth-independent.
- **`--max-commit-files` (auto).** A co-occurrence inside a 50-file migration is weak
  evidence; small focused commits are strong. Auto sets a knee at the **Tukey upper
  fence** `Q3 + 1.5·IQR` of the repo's own commit-size distribution (floored and
  capped), dropping mega/migration/reformat commits that manufacture cheap cliques.
- **High-churn pruning.** Files appearing in >40% of commits are dropped — they
  couple with everything (changelogs, version files).
- **Static denylist.** Known non-source is always skipped: dependency/build trees
  (`node_modules/`, `dist/`, `build/`, `target/`, `vendor/`), caches (`.vscode/`,
  `.idea/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.terraform/`, …),
  lockfiles, sourcemaps/minified, fonts, images.

## 7. Batch cliques and exclusion

A batch-migrated directory (DB schema, generated code) co-changes in bulk, forming a
giant clique that drowns the real signal. Three layers, in order:

1. The **auto commit-size knee** (§6) usually tames it upstream by dropping the bulk
   commits.
2. If a directory still **dominates** the couplings (≥ 50% of all couplings),
   graphmine prints an **advisory** suggesting `--exclude` it (with batch provenance:
   the mean commit size of its changes).
3. Opt-in **`--auto-exclude`** drops a directory only when it passes **all four**
   signals, so a genuinely cohesive component is never dropped:
   - **dominance** ≥ 0.5 of all couplings,
   - **clique density** ≥ 0.5 (within-couplings ÷ possible pairs among the dir's
     *coupling* files),
   - **island-ness** ≥ 0.8 (fraction of the dir's couplings that are internal),
   - **batch provenance** — mean commit size ≥ 2× the repo median.

   It re-mines without the detected dirs and records `meta["auto_excluded"]`. Never on
   by default.

## 8. Limitations

- **Fisher-only couplings.** `--measure chi2|mi|leverage` run the engine but emit no
  couplings — couplings need a p-value to threshold.
- **History-dependent.** New or rarely-changed files have little signal.
- **Correlation, not causation.** Co-change is *evolutionary* coupling — a strong
  heuristic for "what tends to move together," not proof of a code-level dependency.
- **Directional confidence.** The stored coupling is undirected (keeps the best p);
  directional `confidence` is provided per seed in the `by_file` index / blast-radius.

## References

- Hämäläinen, W. *Efficient discovery of the top-K optimal dependency rules with
  Fisher's exact test of significance.* ICDM 2010. — the Kingfisher algorithm.
- Tarone, R. E. *A modified Bonferroni method for discrete data.* Biometrics
  46(2):515–522, 1990. PMID: 2364136. — the effective-number-of-tests correction.
- Hämäläinen, W., & Webb, G. I. *A tutorial on statistically sound pattern
  discovery.* Data Mining and Knowledge Discovery 33, 2019. — background on §5.
