# Snapshot v1 / report v2 contract (tool v0.2)

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
| `require_scores` | false | Every non-placeholder result requires a numeric score; needs score_kind |
| `require_sorted` | false | Known result rank values must be nondecreasing; null placeholders must trail |

Compatible metric/score encodings:

| Metric | Reference distance (smaller is better) | Allowed score kinds |
|---|---|---|
| `l2` | `math.dist(query, document)` | `l2`, `squared_l2` |
| `inner_product` | `-math.fsum(x*y)` | `dot`, `negative_dot` |
| `cosine` | `1 - clamp(fsum(normalized products), -1, 1)` | `cosine_similarity`, `cosine_distance` |

Cosine normalization first divides by each vector's maximum absolute component, then uses `math.hypot` on the scaled values. This avoids subnormal norm distortion. Direct normalized similarity is retained for `cosine_similarity` scores and its negative is used as the rank value; the displayed distance remains 1-similarity. L2/IP rank values equal their displayed distances. Scores may be any finite binary64 value; a very large finite score is retained as mismatch evidence, not silently treated as malformed. Numeric scores without a declared compatible encoding are input errors. A placeholder score must be absent/null; a scored null ID is an invalid-padding finding. Unsupported data does not silently fall back to another metric.

## Ranking and ties

All reference computation uses Python float / IEEE binary64, numerical policy `binary64-scaled-cosine-v2`. “Exhaustive” means every candidate was considered, not exact real arithmetic. Rank ties use **exact equality of computed rank values**, not a tolerance. For cosine, two 1-similarity display distances can round to the same number even though direct similarities differ; v0.2 ranks by negative direct similarity to retain that evidence. This is a documented numerical correction from v0.1. Floating-point near ties can still differ between implementations. `boundary_gap` is the smallest distinct **rank-value** gap to the kth boundary, not a certified error bound; `boundary_distance` and `boundary_rank_value` are separate.

For eligibility set E, let m=min(k, |E|), t=the mth rank value, A=IDs with rank<t, B=IDs with rank==t. Let U be the unique known eligible returned IDs **in the first k raw positions**. Then:

```text
hits = |U intersect A| + min(|U intersect B|, m - |A|)
recall = hits / m                            when m > 0, else null
precision = hits / non-placeholder raw rows  when denominator > 0, else null
```

Duplicate, invalid and unknown rows occupy positions and precision denominator; they gain no extra hit credit. Only properly declared, scoreless null padding is excluded from the precision denominator, but it still consumes a raw position. Rows after k cannot rescue recall or precision, though violations on them are still reported.

Canonical illustrative top-k resolves ties by corpus order. The metric allows any valid boundary tie instead; it is not tied to those canonical IDs. Empty eligibility has null recall even if `min_recall` is set. Correct empty output can pass protocol checks without becoming perfect recall.

Score agreement is `abs(actual - expected) <= score_atol + score_rtol * abs(expected)`. These tolerances never merge rank ties. Squared L2 scores are computed directly as `math.fsum((x-y)**2)`, not by squaring an already-rounded norm; cosine similarity scores likewise use direct normalized similarity, not `1-distance`. Exact bit agreement with a BLAS implementation is not guaranteed. Missing scores remain unverified unless required.

When `require_sorted` is true, consecutive known rows must have nondecreasing rank values; equality is valid. Unknown rows already fail the ID contract; ordering through unknown values is not certified. Proven inversions among known rows, even across unknown rows, are still findings. Null placeholders must trail real results under this policy. Without require_sorted, the auditor makes no order promise.

`missing_strict_count` is the count of A missing from U. Up to five `missing_strict_witnesses` show actual IDs, distances and rank values. Alternative boundary ties are not mandatory merely because they appear in canonical top-k. Displayed witnesses are capped but the total is explicit.

## Findings

Each finding contains a machine-readable `code`, zero-based `row` (null for query-wide findings), and human-readable `detail`.

- `duplicate_id`, `unknown_id`, `ineligible_id`: invalid ownership/membership in the returned sequence.
- `undeclared_padding`, `invalid_padding`: null IDs outside the stated placeholder contract.
- `too_many_results`: raw sequence longer than k; truncation does not conceal the violation.
- `score_mismatch`: supplied score disagrees with its declared encoding within tolerance.
- `missing_score`: require_scores is true but a non-placeholder row has no numeric score.
- `out_of_order`: require_sorted is true and a known row has a better rank value than a preceding known row.
- `non_trailing_padding`: require_sorted is true and a real row follows a null placeholder.
- `recall_budget`: nonempty eligible query falls below explicit `min_recall`; classified separately from protocol violations.

`underfilled` is an observation: fewer unique eligible IDs in the counted window than m. Approximation loss alone does not fail an undeclared quality target. An absent threshold is always visible in report coverage.

## Report and verdict

`audit_snapshot(data, *, max_work=5000000)` returns a private, deterministic JSON-safe result without modifying the input. Audit reports use `schema_version=2`, `report_type=audit`. Fields include `tool_version`, `status`, `metric`, `score_kind`, `rank_policy`, `numerical_policy`, `context_fingerprint`, `coverage`, `summary`, `queries`. Query evidence includes eligibility/effective-k, reference top-k, boundary distance/gap, strict/boundary hit counts, recall, precision, findings, observations and original row evidence.

PASS means no violations of the **declared checks**. FAIL means at least one finding. Unsupported input raises `InputError`; the CLI turns it into ERROR / exit 2. Missing scores and lack of recall threshold must not be read as checked facts. Reports do not contain vectors or timestamps by default; CLI reports add SHA256 of the exact bytes loaded.

## Resource scope

CLI input <=32 MiB. Corpus <=100000 rows, queries <=10000 rows, each returned sequence <=10000 rows. Default scalar budget n*q*d <=5000000; validation checks the first corpus vector shape and refuses before numeric corpus expansion, not just before distance evaluation. Caller can raise `max_work` up to 10^15 deliberately. Independently, cumulative returned rows <=10000, and query count + cumulative returned rows + reference top-k rows <=20000. These evidence budgets apply even at low scalar work and are checked before result copying/report allocation; `max_work` cannot override them. API users are responsible for constructing their Python objects within their memory budget; the CLI byte limit does not apply to an already-materialized dict. Witness overhead is at most five entries per query, always no larger than that query's reference top-k; it is additive to the documented 20000-row accounting. Context normalization/hash serialization and reports are materialized. None of these limits is an RSS promise.

Every query computes reference distances to all supplied corpus rows (including ineligible rows for score evidence), then ranks eligible rows. Runtime is O(q*n*d + q*n*log n + result rows). Full input and report are materialized; it is intended for portable regression snapshots, not full production databases.

## Comparable context and regression reports

`compare_snapshots(baseline, candidate, *, max_recall_drop=0.0, max_work=5000000)` requires **original snapshots**, not reports. Both validate independently. It canonicalizes corpus/query order by ID, effective eligibility by sorted IDs (null and an explicit complete set are equivalent), and the normalized policy defaults. Metric, k, score_kind, score tolerances, min_recall, padding, required scores/order, corpus/query vectors and query/eligibility identities must all match. Changed context produces InputError naming policies/corpus/queries, not a partial comparison over their intersection. Numeric values are binary64-normalized; signed-zero representation differences are conservatively treated as distinct. Context SHA256 excludes results, file whitespace, and timestamps; it is an equality aid, **not a provenance signature**.

Reports use schema_version2/report_type=comparison, with baseline/candidate audit status, context identity, per-query recall delta, added/resolved findings and full candidate audit. Findings are matched by code, row and affected returned ID; residual/detail wording changes within the same finding are not claimed as a new violation. Current candidate evidence retains those values. Empty eligible queries have null deltas.

Comparison FAIL means either the candidate audit fails or at least one query's recall decreases by more than allowed max_recall_drop (finite number in[0,1], bool rejected). The default is zero. A candidate with unchanged protocol failures cannot pass merely because the baseline is equally broken. A mean improvement cannot cancel another query's regression. max_recall_drop does not change either snapshot's declared min_recall or score/order policies.

The CLI checks both input paths and records SHA256 of the exact bytes read for each; those raw hashes are distinct from the comparable-context hash. Each input has its own byte/work/evidence limits, so total comparison work can be twice one audit. No statistical significance or inference about live service quality is made.

## Trust boundary

The caller declares the corpus, metric, filters and scores. A internally consistent but stale/incomplete export can pass. The tool does not verify filter implementation, ACLs, snapshot freshness, provenance, relevance or any live database. It loads no pickle, imports no supplied code, and makes no network calls.

CLI report paths are operator-supplied; they may be outside the input directory. The CLI checks same paths, symlinks and hardlink aliases against all inputs and other outputs. It also compares a regular-file stdout descriptor against those paths before processing: append redirection cannot mutate an input while printing PASS. Such errors go to stderr when it is safe; when both streams alias protected files the error is conveyed by exit2 without writing a diagnostic into them. A closed output pipe flush failure returns2. A shell may truncate a file before the process starts, which cannot be prevented or undone by this program. `--force` only replaces report files. Concurrent hostile changes to filesystem paths are outside the local CLI threat model; use a private output directory. Multi-report output is not transactional. See README for I/O failure behavior.
