# Vector Result Audit

**Your search returned two nearest neighbors. Did it quietly miss the nearest one?**

An offline Python CLI and library for auditing **dense-vector retrieval results**. Export a small regression snapshot, declare its metric and eligible IDs, then inspect per-row evidence for duplicate IDs, filter leaks, wrong score encodings and recall-budget failures.

No database connection. No model download. No API key. No runtime dependencies.

[中文快速开始](README.zh-CN.md) · [Input and numerical contract](docs/contract.md)

## The three-point trap

A query has three eligible neighbors at distances **0, 1, 1**, and requests `k=2`.

| Returned distances | Correct tie-aware recall | Why |
|---|---:|---|
| 0, 1 | 1.0 | The nearest point plus either boundary tie |
| 1, 1 | **0.5** | Two tied points cannot replace the missing nearest point |

A simple “all distances are at most the kth distance” check can miss the second case. This is a hand-constructed test case, **not a claim of a defect in a particular database**. Tie-aware evaluation and exact search are established techniques, not inventions of this project.

## Run it

Python 3.10 or later. From this repository:

```sh
python -m pip install .
vector-audit demo --out audit-demo
```

Open `audit-demo/broken.html` for the offline evidence ledger. The demo writes genuinely audited **synthetic** normal and broken snapshots; it does not contact an engine. The broken examples expose a boundary-tie omission, a filter leak, a squared-L2 score mismatch and a duplicate result.

```sh
vector-audit check audit-demo/clean.json
vector-audit check audit-demo/broken.json --json findings.json --html findings.html
```

The second command intentionally exits **1**. Exit codes:

- **0**: all declared checks pass. Without `min_recall`, this is **not** a recall-quality guarantee.
- **1**: result-contract findings or a failed, explicitly configured recall budget.
- **2**: invalid/unsupported input, exceeded work budget, or output error; no PASS verdict.

`python -m vector_result_audit` is equivalent to `vector-audit`. Package installation is from source or a built wheel; availability on PyPI is not claimed.

## What gets checked

| Check | Meaning |
|---|---|
| Duplicate / unknown IDs | Preserve the original result sequence; duplicates cannot gain extra credit |
| Filter leakage | Returned ID is outside the **supplied** per-query eligibility list |
| Score mismatch | Compare a returned score with the declared metric and score encoding |
| Too many results / padding | Check raw positions and explicit null-padding rules |
| Recall budget | Optional per-query `min_recall`; ANN approximation is not automatically a bug |
| Tied boundary | Alternative exactly tied neighbors are accepted without replacing strictly better ones |

Underfill is an observation unless it violates a declared recall budget. Rows after `k` still get checked but never improve metrics. Empty eligibility yields **N/A**, not recall 1. Missing scores remain explicitly unverified.

## Minimal input

```json
{
  "schema_version": 1,
  "metric": "l2",
  "k": 2,
  "min_recall": 1.0,
  "corpus": [
    {"id": "a", "vector": [0]},
    {"id": "b", "vector": [1]},
    {"id": "c", "vector": [-1]}
  ],
  "queries": [{
    "id": "q",
    "vector": [0],
    "eligible_ids": null,
    "results": [{"id": "b"}, {"id": "c"}]
  }]
}
```

`eligible_ids: null` explicitly means every corpus ID; `[]` means none. IDs are nonempty strings. Scores are optional; when supplied, declare `score_kind`. The specification rejects unknown fields and duplicate JSON keys to catch accidental export mistakes rather than silently ignoring them.

### Python API

```python
from vector_result_audit import audit_snapshot
from vector_result_audit.schema import load_snapshot

report = audit_snapshot(load_snapshot("audit-demo/broken.json"))
for query in report["queries"]:
    print(query["id"], query["recall"], query["findings"])
```

`audit_snapshot()` does not modify input. It returns deterministic JSON-safe evidence; it raises `InputError` instead of returning a partial PASS for an unsupported request. CLI reports add the SHA256 of the exact input bytes read, not an absolute source path.

## Where it fits — and where it does not

[Qdrant already has an ANN Recall UI and CI recipe](https://qdrant.tech/documentation/tutorials-search-engineering/ann-recall/), and [pgvector supports iterative scans for filtering](https://www.postgresql.org/about/news/pgvector-080-released-2952/). Use engine-native tools for live tuning. Use ANN-Benchmarks or VectorDBBench for broad performance benchmarking.

Use this project when you want an **engine-independent, offline artifact** for a test or bug report, with explicit eligibility, raw sequence evidence and score-encoding checks. It does **not** certify:

- embedding relevance, RAG answer quality or statistically significant model improvements;
- completeness/freshness of an exported corpus or correctness of its supplied eligibility lists;
- production ACL implementation, distributed consistency or the health of a live service;
- real-number exactness, quantized scores, sparse/hybrid retrieval, reranking or multivectors.

Reference ranks use exhaustive Python binary64 calculations and **exact equality of computed distances** for ties. Near-equal distances can rank differently in another floating-point implementation; score tolerances do not merge rank ties. See the [numerical contract](docs/contract.md).

## Resource and output safety

The CLI accepts at most **32 MiB** of UTF-8 JSON. Default work budget is **5,000,000 scalar comparisons**, computed conservatively as corpus rows × queries × dimensions before distance computation. Raise it consciously with `--max-work N`; there is no silent sampling. Independently, total returned rows are limited to **10,000**, and queries + returned rows + displayed reference top-k rows to **20,000**. These report-expansion limits are checked before copying results and cannot be raised by `--max-work`. This is a regression-fixture tool, not a billion-vector scan engine. JSON decoding and report materialization use memory; the file/work limits are not a universal RSS guarantee. Inputs are never unpickled or executed.

Report output parents must exist. Existing outputs are refused unless `--force` is explicit; inputs and input aliases are never valid output destinations, even with `--force`. Reports are installed atomically **per file**, not as a multi-file transaction. A filesystem error can leave an earlier report written. No-clobber installation needs hardlink support (normal NTFS and POSIX filesystems); unsupported filesystems return ERROR. Demo requires a new directory and may leave its own partial output if an I/O error occurs.

Treat IDs and returned results as potentially sensitive: reports retain them. Raw vectors are not copied into reports. Review an artifact before sharing it publicly.

## Development and verification

```sh
python -m unittest discover -s tests -v
python scripts/mutation_check.py
python -m pip install build
python -m build
```

Tests include literal counterexamples, actual CLI subprocesses, file-alias protections and an independent `Fraction` oracle that enumerates optimal result sets. Mutation checks run in temporary copies, never modifying the working tree. A passing test count is not evidence of adoption or universal compatibility. CI configuration is provided; remote CI results are only known once it runs on the published repository.

## Contributing

A useful issue includes a **small, shareable snapshot**, the declared metric/score encoding, expected behavior and the audit output. Remove private IDs and vectors before sharing. New adapters need a pinned, actually executed integration test; new metric semantics need independent normal and failure controls. Do not attach credentials or production exports.

Original implementation: MIT. AI-assisted development; technical claims are limited to the documented checks and reproducible tests. No original retrieval algorithm, external adoption or performance speedup is claimed.
