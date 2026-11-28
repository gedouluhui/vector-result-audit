"""Structural regression: retrieval evidence must not scale with corpus size."""
import gc
import math
import tracemalloc
import unittest

from vector_result_audit import audit_snapshot
from vector_result_audit.audit import _query
from vector_result_audit.schema import validate_snapshot


def make_snapshot(corpus_size=20000, dimensions=4, k=10):
    """A deterministic corpus whose IDs are unique but whose vectors repeat."""
    vectors = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    return {
        "schema_version": 1,
        "metric": "l2",
        "k": k,
        "corpus": [{"id": f"doc-{i}", "vector": list(vectors[i % len(vectors)])}
                   for i in range(corpus_size)],
        "queries": [{"id": "q", "vector": [1.0, 0.0, 0.0, 0.0],
                     "eligible_ids": None, "results": []}],
    }


class LargeCorpusBudgetTests(unittest.TestCase):
    def test_large_low_dimensional_corpus_stays_within_work_budget(self):
        data = make_snapshot(corpus_size=20000, dimensions=4, k=10)
        report = audit_snapshot(data)
        self.assertIn(report["status"], ("PASS", "FAIL"))
        self.assertEqual(report["coverage"]["scalar_work"], 20000 * 4)
        self.assertLessEqual(report["coverage"]["scalar_work"], 20000 * 4)

    def test_large_corpus_retains_only_bounded_reference_evidence(self):
        data = make_snapshot(corpus_size=12000, dimensions=4, k=10)
        validated = validate_snapshot(data)
        gc.collect()
        tracemalloc.start()
        try:
            query = _query(validated, validated["queries"][0])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(query["reference_top_k"]), 10)
        self.assertEqual([item["id"] for item in query["reference_top_k"]],
                         [f"doc-{i}" for i in range(0, 40, 4)])
        self.assertEqual(query["strict_neighbor_count"], 0)
        self.assertEqual(query["boundary_gap"], math.sqrt(2))
        # The old implementation retained 12,000 distance/rank/score tuples.
        # Keep generous headroom for validation and report construction.
        self.assertLess(peak, 2_000_000)


if __name__ == "__main__":
    unittest.main()
