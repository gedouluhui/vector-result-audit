"""Independent integer/Fraction oracle: enumerate all optimal result sets."""
from fractions import Fraction
from itertools import combinations, product
import unittest
from vector_result_audit import audit_snapshot


class OracleTests(unittest.TestCase):
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
