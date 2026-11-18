# Actual retrieval outputs, explicit contracts

## What runs

Optional integration environment: Python 3.12; `faiss-cpu==1.16.0`, `qdrant-client==1.20.0`, `numpy==2.5.5`. Core installation does not require any of them.

```sh
python -m pip install .
python -m pip install -r integrations/requirements.txt
python -m unittest discover -s integrations -v
python -m examples.engine_capture --out engine-demo
```

Run from the source directory after installation. The output directory must not exist. The example imports engines only when selected (`--engine faiss`, `qdrant` or default `all`); unavailable dependencies return an error, not a simulated success. Installing these packages can require network access; executing these fixtures does not need a server or downloaded model.

Each engine gets `baseline.json`, `candidate.json`, their JSON/HTML audit reports and `comparison.json`/`comparison.html`. `receipt.json` contains actual versions and control outcomes. Baselines must PASS and injected candidates/comparisons must FAIL or the example exits nonzero. A candidate FAIL is intentional evidence, not a failing integration suite.

## Data-only adapters

```python
from vector_result_audit.adapters import faiss_rows, qdrant_rows, attach_results

# Faiss returns (scores, labels), but the adapter names its inputs explicitly.
D, I = index.search(query_vectors, k)
rows = faiss_rows(labels=I, scores=D, id_map={0: "doc-a", 1: "doc-b"})
snapshot = attach_results(snapshot_template, rows)

# One query's scored points, not a client or connection:
rows = qdrant_rows(response.points, id_map={17: "doc-a", 31: "doc-b"})
```

These helpers do not infer metric/encoding/filters, fetch a corpus, connect to a database, or prove a snapshot is atomic. The template must supply every query, vector and eligibility list. `attach_results` matches result batches to the template's query order and rejects a missing or extra batch.

Explicit provider-ID maps prevent implicit `str()` collisions between integer `1` and string `"1"`. Target IDs must be unique nonempty strings. Unmapped labels are conversion errors, not silently dropped rows. The adapters preserve returned ordering and duplicates.

### Faiss

- `IndexFlatL2` reports **squared** Euclidean distance: use `metric=l2`, `score_kind=squared_l2`.
- `IndexFlatIP` reports dot product: use `metric=inner_product`, `score_kind=dot`.
- Cosine via IndexFlatIP requires normalizing both indexed and query vectors. Keep the declared corpus/query vectors consistent with your exported numerical representation; `metric=cosine`, `score_kind=cosine_similarity`.
- A label `-1` means no result. It becomes null ID/null score at the **same position**; the huge dummy score is not meaningful. Set `allow_null_padding=true`. Other negative/unmapped labels are refused.
- Adapter inputs are bounded nested lists or standard NumPy-style 2-D arrays. Shapes are checked before array-to-list materialization; no streaming iterator or unbounded generator input is accepted.

Reference: [Faiss metric semantics](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances). Behavior was also exercised using the actual pinned wheel, not inferred from docs alone.

### Qdrant client local mode

- `QdrantClient(':memory:')` runs a local implementation, not the Rust server/HNSW cluster.
- `query_points(...).points` contains `ScoredPoint.id` and `.score`. The adapter also accepts corresponding dictionaries; it ignores payload/vector fields rather than copying them into evidence.
- EUCLID returns ordinary L2 (`score_kind=l2`); DOT returns dot; COSINE returns similarity.
- The positive fixture executes an actual payload filter. Expected eligible IDs are constructed from separately known fixture metadata, **not** from returned IDs.
- The negative fixture intentionally omits the application filter while keeping the declared eligibility contract unchanged; the auditor detects the out-of-contract result. This is not a claim that Qdrant violates an executed filter.

Reference: [Qdrant client documentation](https://python-client.qdrant.tech/) and [local-mode examples](https://github.com/qdrant/qdrant-client).

## Coverage and limitations

Integration tests exercise both engines across L2/IP/cosine, Qdrant payload filtering, Faiss padding, wrong score encoding and reverse-order export mistakes. They verify actual response conversion and evidence against explicit small synthetic snapshots. They do not demonstrate ANN recall on real workloads, service APIs/authentication, distributed consistency, cross-version compatibility, real production ACL safety, throughput or human adoption.

Float32 engines and the independent binary64 reference can disagree near ties. The fixtures use separated reference ranks and explicit score tolerance; tolerance does not alter rank membership. To diagnose near ties, inspect the recorded rank values and gap rather than inflating a recall or score threshold until an arbitrary run passes.
