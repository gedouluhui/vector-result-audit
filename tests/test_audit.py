import copy
import json
import math
import unittest

from vector_result_audit import audit_snapshot, InputError


def snapshot(results=None, **extra):
    data = {"schema_version": 1, "metric": "l2", "k": 2,
            "corpus": [{"id": "a", "vector": [0]}, {"id": "b", "vector": [1]}, {"id": "c", "vector": [-1]}],
            "queries": [{"id": "q", "vector": [0], "eligible_ids": None,
                         "results": results if results is not None else [{"id": "a"}, {"id": "b"}]}]}
    data.update(extra)
    return data


class AuditTests(unittest.TestCase):
    def query(self, data):
        return audit_snapshot(data)["queries"][0]

    def codes(self, data):
        return {f["code"] for f in self.query(data)["findings"]}

    def test_clean_alternative_boundary_tie(self):
        data = snapshot([{"id": "a"}, {"id": "c"}])
        report = audit_snapshot(data)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["queries"][0]["recall"], 1.0)
        self.assertEqual(report["queries"][0]["precision"], 1.0)

    def test_boundary_ties_cannot_replace_strictly_better(self):
        q = self.query(snapshot([{"id": "b"}, {"id": "c"}]))
        self.assertEqual(q["hits"], 1)
        self.assertEqual(q["recall"], 0.5)
        self.assertEqual(q["precision"], 0.5)

    def test_duplicate_consumes_slot_without_extra_credit(self):
        data = snapshot([{"id": "a"}, {"id": "a"}])
        q = self.query(data)
        self.assertEqual(q["hits"], 1)
        self.assertEqual(q["precision"], 0.5)
        self.assertIn("duplicate_id", self.codes(data))
        self.assertEqual(audit_snapshot(data)["status"], "FAIL")

    def test_eligibility_applied_before_top_k(self):
        data = snapshot([{"id": "b"}, {"id": "c"}])
        data["queries"][0]["eligible_ids"] = ["b", "c"]
        self.assertEqual(self.query(data)["recall"], 1.0)
        data["queries"][0]["results"] = [{"id": "a"}, {"id": "b"}]
        self.assertIn("ineligible_id", self.codes(data))
        self.assertEqual(self.query(data)["recall"], 0.5)

    def test_unknown_id_retained_as_evidence(self):
        data = snapshot([{"id": "missing"}, {"id": "a"}])
        self.assertIn("unknown_id", self.codes(data))
        q = self.query(data)
        self.assertEqual(q["rows"][0]["id"], "missing")
        self.assertEqual(q["recall"], 0.5)

    def test_extra_rows_cannot_rescue_recall(self):
        data = snapshot([{"id": "b"}, {"id": "c"}, {"id": "a"}])
        self.assertIn("too_many_results", self.codes(data))
        self.assertEqual(self.query(data)["recall"], 0.5)

    def test_empty_eligibility_not_vacuous_recall_one(self):
        data = snapshot([])
        data["queries"][0]["eligible_ids"] = []
        data["min_recall"] = 1.0
        report = audit_snapshot(data)
        self.assertEqual(report["status"], "PASS")
        self.assertIsNone(report["queries"][0]["recall"])
        self.assertIsNone(report["queries"][0]["precision"])
        data["queries"][0]["results"] = [{"id": "a"}]
        self.assertIn("ineligible_id", self.codes(data))

    def test_null_padding_requires_declaration_and_consumes_slot(self):
        data = snapshot([{"id": None}, {"id": "a"}])
        self.assertIn("undeclared_padding", self.codes(data))
        data["allow_null_padding"] = True
        q = self.query(data)
        self.assertNotIn("undeclared_padding", self.codes(data))
        self.assertEqual(q["recall"], 0.5)
        self.assertEqual(q["precision"], 1.0)
        data["queries"][0]["results"][0]["score"] = 1
        data["score_kind"] = "l2"
        self.assertIn("invalid_padding", self.codes(data))

    def test_underfill_is_observation_without_recall_budget(self):
        data = snapshot([{"id": "a"}])
        report = audit_snapshot(data)
        self.assertEqual(report["status"], "PASS")
        self.assertIn("underfilled", self.query(data)["observations"])
        data["min_recall"] = 0.9
        self.assertIn("recall_budget", self.codes(data))
        self.assertEqual(audit_snapshot(data)["status"], "FAIL")

    def test_squared_l2_score_contract(self):
        data = snapshot([{"id": "b", "score": 4}], k=1, score_kind="squared_l2")
        data["corpus"][1]["vector"] = [2]
        self.assertNotIn("score_mismatch", self.codes(data))
        data["queries"][0]["results"][0]["score"] = 2
        self.assertIn("score_mismatch", self.codes(data))

    def test_inner_product_direction_and_score_sign(self):
        data = snapshot([{"id": "b", "score": 1}], metric="inner_product", k=1, score_kind="dot")
        data["queries"][0]["vector"] = [1]
        self.assertEqual(self.query(data)["recall"], 1.0)
        self.assertNotIn("score_mismatch", self.codes(data))
        data["queries"][0]["results"][0]["score"] = -1
        self.assertIn("score_mismatch", self.codes(data))

    def test_cosine_normalization_independent_of_magnitude(self):
        data = {"schema_version": 1, "metric": "cosine", "k": 1, "score_kind": "cosine_similarity",
                "corpus": [{"id": "a", "vector": [100, 0]}, {"id": "b", "vector": [0, 2]}],
                "queries": [{"id": "q", "vector": [3, 0], "eligible_ids": None, "results": [{"id": "a", "score": 1}]}]}
        q = self.query(data)
        self.assertEqual(q["recall"], 1.0)
        self.assertEqual(q["rows"][0]["reference_distance"], 0.0)
        self.assertEqual(q["findings"], [])

    def test_score_tolerance_never_changes_rank(self):
        data = snapshot([{"id": "b"}], k=1, score_atol=1, score_rtol=1)
        self.assertEqual(self.query(data)["recall"], 0.0)

    def test_report_determinism_input_immutability_and_json_safety(self):
        data = snapshot()
        before = copy.deepcopy(data)
        r1 = audit_snapshot(data)
        r2 = audit_snapshot(data)
        self.assertEqual(data, before)
        self.assertEqual(r1, r2)
        self.assertEqual(json.loads(json.dumps(r1, allow_nan=False)), r1)
        self.assertIn("coverage", r1)
        self.assertEqual(r1["summary"]["finding_count"], sum(len(q["findings"]) for q in r1["queries"]))

    def test_boundary_gap_and_effective_k(self):
        data = snapshot(k=10)
        q = self.query(data)
        self.assertEqual(q["effective_k"], 3)
        self.assertEqual(q["recall"], 2 / 3)
        self.assertEqual(q["boundary_distance"], 1.0)
        self.assertEqual(q["boundary_gap"], 1.0)

    def test_boundary_gap_uses_nearest_rank_above_tied_threshold(self):
        data = snapshot([], k=4)
        data["corpus"] = [{"id": str(i), "vector": [value]}
                          for i, value in enumerate((0, 1, 1, 1, 1.5, 2))]
        q = self.query(data)
        self.assertEqual(q["boundary_rank_value"], 1.0)
        self.assertEqual(q["boundary_gap"], 0.5)


class SchemaTests(unittest.TestCase):
    def test_unknown_keys_rejected(self):
        for position in ("top", "corpus", "query", "result"):
            with self.subTest(position=position):
                data = snapshot()
                target = {"top": data, "corpus": data["corpus"][0], "query": data["queries"][0], "result": data["queries"][0]["results"][0]}[position]
                target["typo"] = True
                with self.assertRaises(InputError):
                    audit_snapshot(data)

    def test_bools_nonfinite_and_unsupported_types_rejected(self):
        for value in (True, float("nan"), float("inf"), -float("inf"), "1", 1e101):
            with self.subTest(value=str(value)):
                data = snapshot()
                data["corpus"][0]["vector"][0] = value
                with self.assertRaises(InputError):
                    audit_snapshot(data)
        for key, value in (("schema_version", True), ("schema_version", 1.0), ("k", True), ("k", 0), ("score_atol", -1), ("score_rtol", True), ("min_recall", 1.1), ("allow_null_padding", 1)):
            with self.subTest(key=key):
                data = snapshot(**{key: value})
                with self.assertRaises(InputError):
                    audit_snapshot(data)

    def test_dimensions_duplicates_and_bad_eligibility_rejected(self):
        for defect in ("dimension", "empty", "duplicate", "unknown_eligible", "duplicate_eligible", "missing_eligible"):
            data = snapshot()
            if defect == "dimension": data["queries"][0]["vector"] = [0, 1]
            if defect == "empty": data["corpus"][0]["vector"] = []
            if defect == "duplicate": data["corpus"][1]["id"] = "a"
            if defect == "unknown_eligible": data["queries"][0]["eligible_ids"] = ["unknown"]
            if defect == "duplicate_eligible": data["queries"][0]["eligible_ids"] = ["a", "a"]
            if defect == "missing_eligible": del data["queries"][0]["eligible_ids"]
            with self.subTest(defect=defect), self.assertRaises(InputError):
                audit_snapshot(data)

    def test_budget_refuses_without_partial_pass(self):
        with self.assertRaises(InputError):
            audit_snapshot(snapshot(), max_work=2)
        for budget in (True, 0, -1, 1.5):
            with self.subTest(budget=budget), self.assertRaises(InputError):
                audit_snapshot(snapshot(), max_work=budget)

    def test_zero_cosine_and_incompatible_scores_rejected(self):
        with self.assertRaises(InputError):
            audit_snapshot(snapshot(metric="cosine"))
        with self.assertRaises(InputError):
            audit_snapshot(snapshot(score_kind="dot"))
        with self.assertRaises(InputError):
            audit_snapshot(snapshot([{"id": "a", "score": 0}]))


if __name__ == "__main__":
    unittest.main()
