"""Canonical identity for validated original snapshots, excluding results."""
import hashlib
import json
from .distance import NUMERICAL_POLICY

POLICY_KEYS = ("metric", "k", "score_kind", "score_atol", "score_rtol", "min_recall",
               "allow_null_padding", "require_scores", "require_sorted")


def canonical_context(validated):
    known_count = len(validated["corpus"])
    # Validated eligibility lists are unique subsets. Equal length therefore means
    # all corpus IDs, represented by null rather than repeated N times per query.
    def eligibility(query):
        value = query["eligible_ids"]
        return None if value is None or len(value) == known_count else sorted(value)

    return {"numerical_policy": NUMERICAL_POLICY,
            "policies": {key: validated[key] for key in POLICY_KEYS},
            "corpus": sorted(validated["corpus"], key=lambda item: item["id"]),
            "queries": [{"id": q["id"], "vector": q["vector"],
                         "eligible_ids": eligibility(q)}
                        for q in sorted(validated["queries"], key=lambda item: item["id"])]}


def canonical_bytes(context):
    return json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def context_fingerprint(validated):
    return hashlib.sha256(canonical_bytes(canonical_context(validated))).hexdigest()
