"""Independent exact-rational oracle for real-valued retrieval contracts."""
from fractions import Fraction
from functools import cmp_to_key
from itertools import combinations, product
import random
import unittest
from vector_result_audit import audit_snapshot


def exact_rank(query, vector, metric):
    """Exact comparable rank: squared L2, negative dot, or cosine components."""
    a = [Fraction(x) for x in query]
    b = [Fraction(x) for x in vector]
    if metric == "l2":
        return sum((x - y) ** 2 for x, y in zip(a, b))
    if metric == "inner_product":
        return -sum(x * y for x, y in zip(a, b))
    dot = sum(x * y for x, y in zip(a, b))
    norm_product = sum(x * x for x in a) * sum(y * y for y in b)
    return dot, norm_product


def compare_ranks(left, right, metric):
    if metric != "cosine":
        return (left > right) - (left < right)
    # Compare dot(left)/sqrt(norm_product(left)) exactly by sign and square.
    ldot, lnorm = left
    rdot, rnorm = right
    lsign = (ldot > 0) - (ldot < 0)
    rsign = (rdot > 0) - (rdot < 0)
    if lsign != rsign:
        return -((lsign > rsign) - (lsign < rsign))
    if lsign == 0:
        return 0
    lsquared, rsquared = ldot * ldot * rnorm, rdot * rdot * lnorm
    return -lsign * ((lsquared > rsquared) - (lsquared < rsquared))


def exact_expectation(corpus, query, metric, k, eligible_ids):
    vectors = {item["id"]: item["vector"] for item in corpus}
    eligible = list(vectors) if eligible_ids is None else eligible_ids
    ranks = {rid: exact_rank(query, vectors[rid], metric) for rid in eligible}

    def compare_ids(left, right):
        return compare_ranks(ranks[left], ranks[right], metric)

    ordered = sorted(eligible, key=cmp_to_key(compare_ids))
    m = min(k, len(eligible))
    threshold = ranks[ordered[m - 1]] if m else None
    strict = {rid for rid in eligible if m and compare_ranks(ranks[rid], threshold, metric) < 0}
    boundary = {rid for rid in eligible if m and compare_ranks(ranks[rid], threshold, metric) == 0}
    return m, strict, boundary


class OracleTests(unittest.TestCase):
    def assert_sequences(self, corpus, query, metric, k, eligible_ids=None):
        m, strict, boundary = exact_expectation(corpus, query, metric, k, eligible_ids)
        ids = [item["id"] for item in corpus]
        for returned in product([*ids, "unknown", None], repeat=k):
            with self.subTest(metric=metric, k=k, eligible=eligible_ids, returned=returned):
                data = {"schema_version": 1, "metric": metric, "k": k,
                        "allow_null_padding": True, "corpus": corpus,
                        "queries": [{"id": "q", "vector": query, "eligible_ids": eligible_ids,
                                     "results": [{"id": key} for key in returned]}]}
                report = audit_snapshot(data)["queries"][0]
                eligible = set(ids) if eligible_ids is None else set(eligible_ids)
                counted = set(returned) & eligible
                expected_hits = len(counted & strict) + min(len(counted & boundary), m - len(strict))
                denominator = sum(key is not None for key in returned)
                self.assertEqual(report["hits"], expected_hits)
                self.assertEqual(report["strict_neighbor_count"], len(strict))
                self.assertEqual(report["recall"], expected_hits / m if m else None)
                self.assertEqual(report["precision"], expected_hits / denominator if denominator else None)

    def test_real_valued_metrics_against_exact_rational_oracle(self):
        corpus = [{"id": "a", "vector": [0.1, -0.2, 0.3]},
                  {"id": "b", "vector": [0.2, 0.4, -0.1]},
                  {"id": "c", "vector": [-0.3, 0.1, 0.2]}]
        for metric in ("l2", "inner_product", "cosine"):
            self.assert_sequences(corpus, [0.25, -0.5, 0.75], metric, 2)

    def test_near_ties_remain_distinct_without_score_tolerance(self):
        corpus = [{"id": "best", "vector": [1.0]},
                  {"id": "near", "vector": [1.0 + 2**-40]},
                  {"id": "far", "vector": [1.0 + 2**-20]}]
        for metric in ("l2", "inner_product", "cosine"):
            self.assert_sequences(corpus, [1.0], metric, 2)

    def test_cosine_positive_scaling_invariance(self):
        base = [{"id": "a", "vector": [0.1, 0.2]},
                {"id": "b", "vector": [0.2, -0.4]},
                {"id": "c", "vector": [-0.3, 0.6]}]
        query = [0.3, -0.7]
        expected = audit_snapshot({"schema_version": 1, "metric": "cosine", "k": 2,
                                   "corpus": base, "queries": [{"id": "q", "vector": query,
                                   "eligible_ids": None, "results": [{"id": "a"}, {"id": "b"}]}]})["queries"][0]
        for scale in (1e-200, 1e50):
            corpus = [{"id": item["id"], "vector": [x * scale for x in item["vector"]]} for item in base]
            self.assert_sequences(corpus, [x * scale for x in query], "cosine", 2)
            actual = audit_snapshot({"schema_version": 1, "metric": "cosine", "k": 2,
                                     "corpus": corpus, "queries": [{"id": "q", "vector": [x * scale for x in query],
                                     "eligible_ids": None, "results": [{"id": "a"}, {"id": "b"}]}]})["queries"][0]
            self.assertEqual(actual["hits"], expected["hits"])

    def test_high_dimensional_duplicates_and_filters(self):
        corpus = [{"id": "a", "vector": [((i * 17) % 23 - 11) / 13 for i in range(257)]},
                  {"id": "duplicate-a", "vector": [((i * 17) % 23 - 11) / 13 for i in range(257)]},
                  {"id": "b", "vector": [((i * 29) % 31 - 15) / 17 for i in range(257)]},
                  {"id": "c", "vector": [((i * 37) % 41 - 20) / 19 for i in range(257)]}]
        query = [((i * 43) % 47 - 23) / 29 for i in range(257)]
        for metric in ("l2", "inner_product", "cosine"):
            for eligible in (None, ["a", "b"], ["duplicate-a", "b"], ["b", "c"], []):
                self.assert_sequences(corpus, query, metric, 2, eligible)

    def test_seeded_real_valued_oracle_properties(self):
        rng = random.Random(20261127)
        for case in range(30):
            dimensions = rng.randint(1, 8)
            corpus = [{"id": str(i), "vector": [rng.uniform(-2, 2) for _ in range(dimensions)]}
                      for i in range(4)]
            query = [rng.uniform(-2, 2) for _ in range(dimensions)]
            eligible = None if case % 3 == 0 else rng.sample([item["id"] for item in corpus], rng.randint(0, 4))
            for metric in ("l2", "inner_product", "cosine"):
                self.assert_sequences(corpus, query, metric, 2, eligible)

    def test_exhaustive_small_rankings_against_optimal_sets(self):
        ids, values = ["a", "b", "c"], [-1, 0, 1]
        checked = 0
        for metric in ("l2", "inner_product"):
            for qvalue in (-1, 0, 1):
                distances = {key: (Fraction(value - qvalue) ** 2 if metric == "l2" else -Fraction(value * qvalue)) for key, value in zip(ids, values)}
                for mask in range(8):
                    eligible = [key for i, key in enumerate(ids) if mask & (1 << i)]
                    for k in (1, 2, 3):
                        m = min(k, len(eligible))
                        choices = list(combinations(eligible, m))
                        totals = [sum(distances[key] for key in choice) for choice in choices]
                        best = [set(choice) for choice, total in zip(choices, totals) if total == min(totals)]
                        for returned in product([*ids, "unknown", None], repeat=k):
                            valid = set(returned) & set(eligible)
                            expected_hits = max(len(valid & answer) for answer in best)
                            data = {"schema_version": 1, "metric": metric, "k": k, "allow_null_padding": True,
                                    "corpus": [{"id": key, "vector": [value]} for key, value in zip(ids, values)],
                                    "queries": [{"id": "q", "vector": [qvalue], "eligible_ids": eligible,
                                                 "results": [{"id": key} for key in returned]}]}
                            report = audit_snapshot(data)["queries"][0]
                            self.assertEqual(report["hits"], expected_hits, (metric, qvalue, eligible, k, returned))
                            self.assertEqual(report["recall"], expected_hits / m if m else None)
                            denominator = sum(key is not None for key in returned)
                            self.assertEqual(report["precision"], expected_hits / denominator if denominator else None)
                            checked += 1
        self.assertEqual(checked, 7440)


if __name__ == "__main__":
    unittest.main()
