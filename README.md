# Vector Result Audit

**Catch a broken retrieval export before it becomes a RAG regression.**

Offline contracts for dense-vector search: explicit filtering, score encodings, result order, missing-neighbor evidence, and **before/after comparisons that refuse incomparable datasets**.

No runtime dependencies. No API keys. No model download. JSON and standalone HTML stay local.

[Live example](https://gedouluhui.github.io/vector-result-audit/) · [中文](README.zh-CN.md) · [Input contract](docs/contract.md) · [Real Faiss / Qdrant examples](docs/integrations.md) · [Releases](https://github.com/gedouluhui/vector-result-audit/releases) · [CI](https://github.com/gedouluhui/vector-result-audit/actions)

## Start with the failure, not a dashboard

Three eligible neighbors are at distances **0, 1, 1**. You ask for two, and get the last two.

| Returned distances | Tie-aware recall | Evidence |
|---|---:|---|
| 0, 1 | 1.0 | Closest neighbor plus either boundary tie |
| 1, 1 | **0.5** | Missing strictly-better neighbor at distance 0 |

The report names the missing ID. It does not confuse a different valid tie with a defect. This is a constructed counterexample, not a claim of an upstream database bug; exact search and tie-aware evaluation are established techniques.

## Run in a minute

Python **3.10+**. Install from source, or download the wheel from Releases:

```sh
python -m pip install .
vector-audit demo --out audit-demo
vector-audit check audit-demo/clean.json
vector-audit check audit-demo/broken.json --json findings.json --html findings.html
```

Open `audit-demo/broken.html`. The last command intentionally exits **1** because the synthetic input contains errors. `python -m vector_result_audit` is equivalent to the console command. PyPI availability is not claimed.

## What changed between runs?

Use two **original snapshots**, not precomputed reports:

```sh
vector-audit compare before.json after.json --json regression.json --html regression.html
vector-audit compare before.json after.json --max-recall-drop 0.02
```

Before calculating a delta, the tool verifies identical corpus vectors, queries, effective eligibility, metric, k and audit policies. ID ordering and explicit-all versus null eligibility are normalized. A changed corpus or threshold produces **ERROR**, not an attractive but meaningless comparison.

Every query is gated separately: a mean improvement cannot hide one regressed query. Candidate contract failures cannot be waived by the recall-drop budget. This is a deterministic regression gate, **not a statistical significance test**.

The `clean` and `broken` built-in demos intentionally contain different query sets; do not compare those two as if they were the same experiment. The [engine example](docs/integrations.md) produces a comparable baseline/candidate pair.

## From actual retrieval results

The core remains dependency-free. Data-only adapters accept real library results without connecting to a service:

```python
from vector_result_audit import audit_snapshot, compare_snapshots
from vector_result_audit.adapters import faiss_rows, qdrant_rows, attach_results

# D, I = index.search(query_vectors, k)
rows = faiss_rows(I, D, id_map={0: "doc-a", 1: "doc-b"})
captured = attach_results(snapshot, rows)
report = audit_snapshot(captured)

# response = client.query_points(...)
rows = qdrant_rows(response.points, id_map={17: "doc-a", 31: "doc-b"})
```

ID maps are explicit and one-to-one. Raw order and duplicates survive conversion. Faiss `-1` is translated to a null placeholder in the same position; only its meaningless sentinel score is dropped. Declare the metric, score encoding and padding policy in the snapshot rather than relying on guesses.

For a **real executable** example with no server:

```sh
# Optional: Python 3.12, separate environment recommended
python -m pip install -r integrations/requirements.txt
python -m examples.engine_capture --out engine-demo
```

This runs CPU Faiss IndexFlat and Qdrant-client's in-memory mode. It saves actual snapshots, audit reports and comparisons. The candidate defects are explicitly injected (duplicate a returned row / omit an application filter), not discoveries of bugs in either engine. These tests do not certify server-side Qdrant, ANN quality, production ACLs or performance.

## Checks you can declare

| Check | Behavior |
|---|---|
| Duplicate / unknown / ineligible IDs | Keep original positions; invalid items gain no credit |
| Score encoding | L2 vs squared L2, dot vs negative dot, cosine similarity vs distance |
| `require_scores: true` | Missing non-placeholder scores are findings; needs `score_kind` |
| `require_sorted: true` | Detect inversions in reference rank values and non-trailing null padding |
| `min_recall` | Explicit per-query recall budget, optional by default |
| Strict-neighbor witness | Names up to five missing strictly-better IDs and reports the full count |
| Comparable context | SHA256 of canonical corpus/query/eligibility/policies, excluding results |

Empty eligibility has **N/A** recall, not 1. Rows after k cannot rescue metrics but are still audited. Underfill alone is an observation, not automatically a bug. Missing scores are unverified unless required.

### Minimal snapshot

```json
{
  "schema_version": 1,
  "metric": "l2",
  "k": 2,
  "min_recall": 1.0,
  "require_sorted": true,
  "corpus": [
    {"id": "a", "vector": [0]},
    {"id": "b", "vector": [1]},
    {"id": "c", "vector": [-1]}
  ],
  "queries": [{
    "id": "q", "vector": [0], "eligible_ids": null,
    "results": [{"id": "b"}, {"id": "c"}]
  }]
}
```

`eligible_ids: null` means all corpus IDs; `[]` means none. Unknown fields, duplicate JSON keys, booleans in numeric fields and unsupported inputs are rejected. v0.1 snapshots remain valid; the new required-score/order flags default to false. v0.2 report JSON uses **schema 2** with an explicit numerical policy and context fingerprint.

## Exit codes and CI

- **0:** declared checks pass. Without `min_recall`, this is **not** a recall-quality guarantee.
- **1:** result findings, an explicit recall-budget failure, or a comparison regression.
- **2:** invalid/incomparable input, exceeded budget, or output failure. Not PASS.

Use `--json` and `--html`, then upload those files in your CI's `always()` step. Do not hide exit 1/2 with `|| true`; the artifact upload and gate outcome serve different jobs. This repository's CI runs core tests, negative controls, clean package installation and separately pinned real-engine integrations, retaining evidence artifacts on failure.

## Numerical policy, scope and safety

v0.2 computes direct score encodings and scaled cosine normalization. Cosine is ranked by **negative direct similarity**, rather than subtracting tiny similarities from 1 and losing them. The displayed cosine distance is still 1-similarity; two displayed distances may therefore match while precise rank values differ. Rank-value ties are exact binary64 equality. Score tolerance never merges ranks. This deliberately corrects tiny-boundary behavior from v0.1; it is not exact real-number arithmetic. See [the contract](docs/contract.md).

Default CLI input limit: **32 MiB**. Conservative scalar budget: **5,000,000** (`corpus × queries × dimensions`), checked before corpus expansion. Independent caps: **10,000 total result rows**, **20,000 query + result + reference rows**. `--max-work` changes only the scalar budget. Comparison applies each input's bounds separately and can cost twice an audit. Full JSON/results are materialized; these bounds are not an RSS guarantee or a billion-vector performance claim.

Explicit output files cannot alias either input; stdout file-descriptor aliases are rejected too. Append redirection to an input is refused, but **a shell's `>` truncation occurs before Python starts and cannot be undone**. Broken output pipes return ERROR/2. Report writes are atomic per file, not one transaction; earlier files can remain after a later I/O failure. No-clobber mode requires filesystem hardlink support. Use a private output directory; hostile concurrent path replacement is outside this local CLI's threat model.

Reports retain IDs, returned scores and findings; review them before sharing. Raw vectors are not copied into the reports. No unpickling or supplied-code execution occurs in the CLI. Python API callers must treat their Python objects as trusted code, not a sandbox.

## Why not just use an engine benchmark?

[Qdrant already has an ANN Recall UI and CI recipe](https://qdrant.tech/documentation/tutorials-search-engineering/ann-recall/); [pgvector has iterative scanning for filtering](https://www.postgresql.org/about/news/pgvector-080-released-2952/). ANN-Benchmarks and VectorDBBench cover broad benchmarks. Use those for live tuning/performance.

This project produces a small **engine-independent, shareable result contract** from an explicit export. It cannot prove the export is complete/atomic/current, that the supplied eligibility list implements your ACL, or that embeddings/RAG answers are relevant. Sparse/hybrid/multivector/reranked retrieval and quantized-score certification are outside scope.

## Contribute and verify

```sh
python -m unittest discover -s tests -v
python scripts/mutation_check.py
python -m pip install build
python -m build
# In the optional pinned integration environment:
python -m unittest discover -s integrations -v
```

Core tests include actual subprocess I/O failures and an independent Fraction/optimal-set oracle. Mutation tests operate on disposable copies and refuse crashes as evidence of catching a bug. Actual library tests do not silently skip missing engines. See [v0.2 verification notes](docs/verification.md) for what was and was not measured.

Useful contributions start with a minimal non-private snapshot, expected contract and evidence. Never submit production credentials, raw private exports, or unsupported claims of upstream defects. Original code: MIT. AI-assisted implementation; no algorithm-originality, universal speedup, external-adoption or star-growth claims.
