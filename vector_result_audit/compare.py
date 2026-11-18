"""Compare original snapshots only after establishing an identical context."""
from .audit import audit_snapshot, VERSION
from .context import canonical_context, canonical_bytes
from .schema import validate_snapshot, _number, InputError, DEFAULT_MAX_WORK


def _finding_keys(query):
    rows = query["rows"]
    return {(item["code"], item["row"], rows[item["row"]]["id"] if item["row"] is not None else None): item
            for item in query["findings"]}


def compare_snapshots(baseline, candidate, *, max_recall_drop=0.0, max_work=DEFAULT_MAX_WORK):
    """FAIL for an invalid candidate or any per-query recall loss beyond budget.

    Each input has its own max_work limit; total comparison work may be twice it.
    This is a deterministic regression gate, not a statistical significance test.
    """
    allowed = _number(max_recall_drop, "max_recall_drop", 0, 1)
    before = validate_snapshot(baseline, max_work=max_work)
    after = validate_snapshot(candidate, max_work=max_work)
    a, b = canonical_context(before), canonical_context(after)
    for key in ("policies", "corpus", "queries"):
        if canonical_bytes(a[key]) != canonical_bytes(b[key]):
            raise InputError(f"incomparable {key}: corpus, queries, eligibility and audit policies must match; only results may change")
    old = audit_snapshot(before, max_work=max_work)
    new = audit_snapshot(after, max_work=max_work)
    old_by_id = {q["id"]: q for q in old["queries"]}
    changes = []
    for q in new["queries"]:
        prior = old_by_id[q["id"]]
        delta = q["recall"] - prior["recall"] if q["recall"] is not None else None
        old_findings, new_findings = _finding_keys(prior), _finding_keys(q)
        changes.append({"id": q["id"], "baseline_recall": prior["recall"], "candidate_recall": q["recall"],
                        "recall_delta": delta, "recall_regression": delta is not None and delta < -allowed,
                        "added_findings": [v for k,v in new_findings.items() if k not in old_findings],
                        "resolved_findings": [v for k,v in old_findings.items() if k not in new_findings]})
    regressions = sum(q["recall_regression"] for q in changes)
    return {"schema_version": 2, "report_type": "comparison", "tool_version": VERSION,
            "status": "FAIL" if regressions or new["status"] == "FAIL" else "PASS",
            "context_fingerprint": new["context_fingerprint"], "numerical_policy": new["numerical_policy"],
            "max_recall_drop": allowed, "baseline_status": old["status"], "candidate_status": new["status"],
            "summary": {"query_count": len(changes), "recall_regressions": regressions,
                        "added_findings": sum(len(q["added_findings"]) for q in changes),
                        "resolved_findings": sum(len(q["resolved_findings"]) for q in changes)},
            "queries": changes, "candidate_audit": new,
            "limitations": ["Only identical declared corpus, query, eligibility and policy contexts are compared.",
                            "Candidate audit failures cannot be waived by the recall-drop budget.",
                            "Each snapshot has its own work limit; comparison can cost twice a single audit.",
                            "No statistical significance, engine performance, relevance or live-system correctness is inferred."]}
