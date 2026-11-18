"""Raw-sequence contract checks with strict-neighbor-preserving tie credit."""
from .schema import DEFAULT_MAX_WORK, validate_snapshot
from .distance import reference, NUMERICAL_POLICY
from .context import context_fingerprint

VERSION = "0.2.1"
RANK_POLICY = "exhaustive binary64; exact rank-value ties; cosine ranked by negative direct similarity; score tolerance does not change ranks"


def _query(data, query):
    k, metric = data["k"], data["metric"]
    references = {item["id"]: reference(query["vector"], item["vector"], metric, data["score_kind"])
                  for item in data["corpus"]}
    distances = {rid: values[0] for rid, values in references.items()}
    ranks = {rid: values[1] for rid, values in references.items()}
    eligible = set(distances) if query["eligible_ids"] is None else set(query["eligible_ids"])
    ordered = sorted((rid for rid in distances if rid in eligible), key=ranks.__getitem__)
    m = min(k, len(eligible))
    threshold = ranks[ordered[m - 1]] if m else None
    strict = {rid for rid in eligible if ranks[rid] < threshold} if m else set()
    boundary = {rid for rid in eligible if ranks[rid] == threshold} if m else set()
    gaps = [abs(d - threshold) for rid, d in ranks.items() if rid in eligible and d != threshold] if m else []
    findings, observations, evidence = [], [], []

    def finding(code, row, detail):
        findings.append({"code": code, "row": row, "detail": detail})

    if len(query["results"]) > k:
        finding("too_many_results", None, f"returned {len(query['results'])} raw rows for k={k}; only the first k positions count")
    seen, counted = set(), set()
    denominator = 0
    score_checked = score_missing = 0
    previous_rank = None
    previous_row = None
    padding_seen = False
    for index, row in enumerate(query["results"]):
        rid, score = row["id"], row["score"]
        declared_placeholder = rid is None and data["allow_null_padding"] and score is None
        if index < k and not declared_placeholder:
            denominator += 1
        ref = distances.get(rid)
        is_eligible = rid in eligible
        creditable = index < k and is_eligible and rid not in seen
        expected = error = None
        if rid is None:
            padding_seen = True
            if not data["allow_null_padding"]:
                finding("undeclared_padding", index, "null ID was not declared as padding")
            if score is not None:
                finding("invalid_padding", index, "padding cannot carry a numeric score")
        else:
            if data["require_sorted"]:
                if padding_seen:
                    finding("non_trailing_padding", index, "real result follows a null placeholder")
                if rid in ranks:
                    current_rank = ranks[rid]
                    if previous_rank is not None and current_rank < previous_rank:
                        finding("out_of_order", index, f"rank value {current_rank!r} is better than row {previous_row} value {previous_rank!r}")
                    previous_rank, previous_row = current_rank, index
            if rid in seen:
                finding("duplicate_id", index, f"ID {rid!r} already occurred in this returned sequence")
            if rid not in distances:
                finding("unknown_id", index, f"ID {rid!r} is absent from the declared corpus")
            elif not is_eligible:
                finding("ineligible_id", index, f"ID {rid!r} is outside this query's eligibility set")
            if creditable:
                counted.add(rid)
            seen.add(rid)
            if score is not None and ref is not None:
                expected = references[rid][2]
                error = abs(score - expected)
                score_checked += 1
                if error > data["score_atol"] + data["score_rtol"] * abs(expected):
                    finding("score_mismatch", index, f"observed {score!r}; expected {expected!r} under {data['score_kind']}; absolute residual {error!r}")
            elif score is None:
                score_missing += 1
                if data["require_scores"]:
                    finding("missing_score", index, "non-placeholder result requires a numeric score")
        evidence.append({"row": index, "id": rid, "score": score, "reference_distance": ref,
                         "rank_value": ranks.get(rid),
                         "expected_score": expected, "score_error": error, "eligible": is_eligible,
                         "within_k": index < k, "counted_unique_eligible": creditable,
                         "declared_placeholder": declared_placeholder})
    strict_hits = len(counted & strict)
    boundary_hits = min(len(counted & boundary), m - len(strict))
    hits = strict_hits + boundary_hits
    recall = hits / m if m else None
    precision = hits / denominator if denominator else None
    if len(counted) < m:
        observations.append("underfilled")
    if data["min_recall"] is not None and recall is not None and recall < data["min_recall"]:
        finding("recall_budget", None, f"recall {recall!r} is below declared minimum {data['min_recall']!r}; this is a quality budget, not automatically an engine bug")
    missing = [rid for rid in ordered[:m] if rid in strict and rid not in counted]
    return {"id": query["id"], "eligible_count": len(eligible), "effective_k": m,
            "reference_top_k": [{"id": rid, "distance": distances[rid], "rank_value": ranks[rid],
                                 "strict": rid in strict, "returned": rid in counted} for rid in ordered[:m]],
            "missing_strict_count": len(missing),
            "missing_strict_witnesses": [{"id": rid, "distance": distances[rid], "rank_value": ranks[rid]} for rid in missing[:5]],
            "boundary_distance": distances[ordered[m - 1]] if m else None,
            "boundary_rank_value": threshold, "boundary_gap": min(gaps) if gaps else None,
            "strict_neighbor_count": len(strict), "strict_hits": strict_hits, "boundary_hits": boundary_hits,
            "hits": hits, "recall": recall, "precision": precision,
            "score_checked_rows": score_checked, "score_missing_rows": score_missing,
            "findings": findings, "observations": observations, "rows": evidence}


def audit_snapshot(data, *, max_work=DEFAULT_MAX_WORK):
    """Audit caller-declared data. PASS does not certify snapshot provenance."""
    data = validate_snapshot(data, max_work=max_work)
    queries = [_query(data, query) for query in data["queries"]]
    findings = [f for q in queries for f in q["findings"]]
    recalls = [q["recall"] for q in queries if q["recall"] is not None]
    quality = sum(f["code"] == "recall_budget" for f in findings)
    return {"schema_version": 2, "report_type": "audit", "tool_version": VERSION,
            "numerical_policy": NUMERICAL_POLICY, "context_fingerprint": context_fingerprint(data),
            "status": "FAIL" if findings else "PASS",
            "metric": data["metric"], "score_kind": data["score_kind"], "rank_policy": RANK_POLICY,
            "coverage": {"recall_threshold": data["min_recall"],
                         "require_scores": data["require_scores"], "require_sorted": data["require_sorted"],
                         "score_atol": data["score_atol"], "score_rtol": data["score_rtol"],
                         "score_checked_rows": sum(q["score_checked_rows"] for q in queries),
                         "score_missing_rows": sum(q["score_missing_rows"] for q in queries),
                         "scalar_work": len(data["corpus"]) * len(data["queries"]) * len(data["corpus"][0]["vector"]),
                         "limitations": ["Only the supplied snapshot and eligibility lists are checked.",
                                         "Exhaustive binary64 is not exact real-number arithmetic; near ties may differ across implementations.",
                                         "Without min_recall, PASS checks protocol and declared scores only.",
                                         "Missing scores are unverified. No embedding relevance, ACL implementation, database freshness or snapshot completeness is certified."]},
            "summary": {"query_count": len(queries), "finding_count": len(findings),
                        "contract_violations": len(findings) - quality, "recall_budget_failures": quality,
                        "mean_recall": sum(recalls) / len(recalls) if recalls else None},
            "queries": queries}
