# Snapshot and numerical contract (v1)

## Input

A UTF-8 JSON object; duplicate keys and unknown fields are errors. Required fields: integer `schema_version: 1`, `metric`, positive integer `k` (<=10000), nonempty `corpus`, nonempty `queries`. Boolean is never accepted as a number.

Corpora contain `{id, vector}`. Queries contain `{id, vector, eligible_ids, results}`. Result rows contain `id` and optional `score`. Document/query IDs are unique nonempty Unicode strings of <=256 characters; result IDs can be duplicate or unknown because those are audit findings. IDs are case-sensitive and not Unicode-normalized. Corpus IDs need not differ from query IDs: there is no implicit self-exclusion.

Vectors have equal positive dimension <=4096. Entries are finite numeric values with magnitude <=1e100. Zero-norm cosine inputs are errors. `eligible_ids` must be present: null means all corpus IDs; a list must contain unique known IDs; `[]` means none.

Optional top-level settings:

| Field | Default | Meaning |
|---|---|---|
| `score_kind` | null | Explicit score encoding; needed for numeric returned scores |
| `score_atol` | 1e-8 | Absolute score tolerance, finite [0,1] |
| `score_rtol` | 1e-6 | Relative score tolerance, finite [0,1] |
| `min_recall` | null | Optional per-query quality budget, finite [0,1] |
| `allow_null_padding` | false | Null IDs are explicit placeholders only when true |

Compatible metric/score encodings:

| Metric | Reference distance (smaller is better) | Allowed score kinds |
|---|---|---|
| `l2` | `math.dist(query, document)` | `l2`, `squared_l2` |
| `inner_product` | `-math.fsum(x*y)` | `dot`, `negative_dot` |
| `cosine` | `1 - clamp(fsum(normalized products), -1, 1)` | `cosine_similarity`, `cosine_distance` |

Cosine normalization uses `math.hypot`. Scores may be any finite binary64 value; a very large finite score is retained as mismatch evidence, not silently treated as malformed. Numeric scores without a declared compatible encoding are input errors. A placeholder score must be absent/null; a scored null ID is an invalid-padding finding. Unsupported data does not silently fall back to another metric.

## Ranking and ties

All reference computation uses Python float / IEEE binary64. “Exhaustive” means every candidate was considered, not exact real arithmetic. Rank ties use **exact equality of computed reference distances**, not a tolerance. Floating-point near ties may legitimately differ between implementations. The report records the smallest distinct distance gap from the kth boundary where one exists; it is context, not a certified error bound.

For eligibility set E, let m=min(k, |E|), t=the mth reference distance, A=IDs strictly closer than t, B=IDs exactly at t. Let U be the unique known eligible returned IDs **in the first k raw positions**. Then:

```text
hits = |U intersect A| + min(|U intersect B|, m - |A|)
recall = hits / m                            when m > 0, else null
precision = hits / non-placeholder raw rows  when denominator > 0, else null
```

Duplicate, invalid and unknown rows occupy positions and precision denominator; they gain no extra hit credit. Only properly declared, scoreless null padding is excluded from the precision denominator, but it still consumes a raw position. Rows after k cannot rescue recall or precision, though violations on them are still reported.

Canonical illustrative top-k resolves ties by corpus order. The metric allows any valid boundary tie instead; it is not tied to those canonical IDs. Empty eligibility has null recall even if `min_recall` is set. Correct empty output can pass protocol checks without becoming perfect recall.

Score agreement is `abs(actual - expected) <= score_atol + score_rtol * abs(expected)`. These tolerances never merge rank ties. Squared L2 is the computed L2 value squared. Exact bit agreement with a BLAS sum-of-squares implementation is not guaranteed. Missing scores remain unverified.

## Findings

Each finding contains a machine-readable `code`, zero-based `row` (null for query-wide findings), and human-readable `detail`.

- `duplicate_id`, `unknown_id`, `ineligible_id`: invalid ownership/membership in the returned sequence.
- `undeclared_padding`, `invalid_padding`: null IDs outside the stated placeholder contract.
- `too_many_results`: raw sequence longer than k; truncation does not conceal the violation.
- `score_mismatch`: supplied score disagrees with its declared encoding within tolerance.
- `recall_budget`: nonempty eligible query falls below explicit `min_recall`; classified separately from protocol violations.

`underfilled` is an observation: fewer unique eligible IDs in the counted window than m. Approximation loss alone does not fail an undeclared quality target. An absent threshold is always visible in report coverage.

## Report and verdict

`audit_snapshot(data, *, max_work=5000000)` returns a private, deterministic JSON-safe result without modifying the input. Fields include `schema_version`, `tool_version`, `status`, `metric`, `score_kind`, `rank_policy`, `coverage`, `summary`, `queries`. Query evidence includes eligibility/effective-k, reference top-k, boundary distance/gap, strict/boundary hit counts, recall, precision, findings, observations and original row evidence.

PASS means no violations of the **declared checks**. FAIL means at least one finding. Unsupported input raises `InputError`; the CLI turns it into ERROR / exit 2. Missing scores and lack of recall threshold must not be read as checked facts. Reports do not contain vectors or timestamps by default; CLI reports add SHA256 of the exact bytes loaded.

## Resource scope

CLI input <=32 MiB. Corpus <=100000 rows, queries <=10000 rows, each returned sequence <=10000 rows. Default scalar budget n*q*d <=5000000; validation refuses before distance evaluation. Caller can raise `max_work` up to 10^15 deliberately. Independently, cumulative returned rows <=10000, and query count + cumulative returned rows + reference top-k rows <=20000. These evidence budgets apply even at low scalar work and are checked before result copying/report allocation; `max_work` cannot override them. API users are responsible for constructing their Python objects within their memory budget; the CLI byte limit does not apply to an already-materialized dict. Neither limit is an RSS promise.

Every query computes reference distances to all supplied corpus rows (including ineligible rows for score evidence), then ranks eligible rows. Runtime is O(q*n*d + q*n*log n + result rows). Full input and report are materialized; it is intended for portable regression snapshots, not full production databases.

## Trust boundary

The caller declares the corpus, metric, filters and scores. A internally consistent but stale/incomplete export can pass. The tool does not verify filter implementation, ACLs, snapshot freshness, provenance, relevance or any live database. It loads no pickle, imports no supplied code, and makes no network calls.

CLI report paths are operator-supplied; they may be outside the input directory. The CLI checks same paths, symlinks and hardlink aliases against its input and other outputs. `--force` only replaces report files. Concurrent hostile changes to filesystem paths are outside the local CLI threat model; use a private output directory. Multi-report output is not transactional. See README for I/O failure behavior.
