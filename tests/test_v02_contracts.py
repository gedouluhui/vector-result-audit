import copy
import json
import unittest
from vector_result_audit import audit_snapshot, InputError
from vector_result_audit.schema import validate_snapshot
from test_audit import snapshot


def codes(report):
    return {f['code'] for q in report['queries'] for f in q['findings']}


class NumericalCorrections(unittest.TestCase):
    def tiny_cosine(self, score):
        return {'schema_version': 1, 'metric': 'cosine', 'k': 1,
                'score_kind': 'cosine_similarity', 'score_atol': 0, 'score_rtol': 0,
                'corpus': [{'id': 'near', 'vector': [1e-20, 1]}, {'id': 'orthogonal', 'vector': [0, 1]}],
                'queries': [{'id': 'q', 'vector': [1, 0], 'eligible_ids': None,
                             'results': [{'id': 'near', 'score': score}]}]}

    def test_direct_cosine_score_not_cancelled_by_distance(self):
        r = audit_snapshot(self.tiny_cosine(1e-20))
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual(r['queries'][0]['rows'][0]['expected_score'], 1e-20)
        self.assertIn('score_mismatch', codes(audit_snapshot(self.tiny_cosine(0))))

    def test_cosine_rank_preserves_small_similarity(self):
        data = self.tiny_cosine(0)
        data['queries'][0]['results'] = [{'id': 'orthogonal', 'score': 0}]
        self.assertEqual(audit_snapshot(data)['queries'][0]['recall'], 0.0)

    def test_subnormal_direction_matches_scaled_direction(self):
        data = self.tiny_cosine(1)
        data['score_atol'] = 1e-12
        data['corpus'] = [{'id': 'near', 'vector': [1e-323, 1e-323]}, {'id': 'orthogonal', 'vector': [1, 1]}]
        data['queries'][0]['vector'] = [1e-323, 1e-323]
        r = audit_snapshot(data)
        self.assertEqual(r['status'], 'PASS')
        self.assertAlmostEqual(r['queries'][0]['rows'][0]['expected_score'], 1.0, places=14)
        self.assertEqual(r['queries'][0]['recall'], 1.0)

    def test_work_budget_precedes_numeric_copy(self):
        data = snapshot()
        data['corpus'][0]['vector'] = [object()]
        with self.assertRaisesRegex(InputError, 'work budget exceeded'):
            validate_snapshot(data, max_work=1)


class ExplicitContracts(unittest.TestCase):
    def test_required_scores_refuse_missing_not_padding(self):
        data = snapshot([{'id': 'a'}, {'id': None}], score_kind='l2', require_scores=True, allow_null_padding=True)
        r = audit_snapshot(data)
        self.assertEqual([f['row'] for f in r['queries'][0]['findings'] if f['code']=='missing_score'], [0])
        self.assertEqual(r['status'], 'FAIL')
        data['queries'][0]['results'][0]['score'] = 0
        self.assertEqual(audit_snapshot(data)['status'], 'PASS')

    def test_required_scores_need_encoding_and_strict_boolean(self):
        with self.assertRaises(InputError):
            audit_snapshot(snapshot(require_scores=True))
        for key in ('require_scores', 'require_sorted'):
            for val in (1, 'true', None):
                with self.subTest(key=key, val=val), self.assertRaises(InputError):
                    audit_snapshot(snapshot(**{key: val}))

    def test_sorting_catches_reverse_even_with_full_recall(self):
        data = snapshot([{'id': 'b'}, {'id': 'a'}], require_sorted=True)
        r = audit_snapshot(data)
        self.assertEqual(r['queries'][0]['recall'], 1.0)
        self.assertIn('out_of_order', codes(r))
        data['require_sorted'] = False
        self.assertEqual(audit_snapshot(data)['status'], 'PASS')

    def test_sorting_allows_ties_and_requires_trailing_padding(self):
        data = snapshot([{'id':'b'}, {'id':'c'}], require_sorted=True)
        self.assertNotIn('out_of_order', codes(audit_snapshot(data)))
        data['allow_null_padding'] = True
        data['queries'][0]['results'] = [{'id':None}, {'id':'a'}]
        self.assertIn('non_trailing_padding', codes(audit_snapshot(data)))
        data['queries'][0]['results'].reverse()
        self.assertNotIn('non_trailing_padding', codes(audit_snapshot(data)))

    def test_missing_strict_witnesses_not_canonical_tie_difference(self):
        r = audit_snapshot(snapshot([{'id':'b'}, {'id':'c'}]))['queries'][0]
        self.assertIn('missing_strict_witnesses', r)
        self.assertEqual(r['missing_strict_count'], 1)
        self.assertEqual(r['missing_strict_witnesses'], [{'id':'a', 'distance':0.0, 'rank_value':0.0}])
        q = audit_snapshot(snapshot([{'id':'a'}, {'id':'c'}]))['queries'][0]
        self.assertEqual(q['missing_strict_count'], 0)
        self.assertEqual(q['missing_strict_witnesses'], [])

    def test_witnesses_are_capped_but_total_is_explicit(self):
        data = snapshot([], k=20)
        data['corpus'] = [{'id':str(i), 'vector':[i]} for i in range(30)]
        q = audit_snapshot(data)['queries'][0]
        self.assertIn('missing_strict_witnesses', q)
        self.assertEqual(q['missing_strict_count'], 19)
        self.assertEqual(len(q['missing_strict_witnesses']), 5)


class ContextIdentity(unittest.TestCase):
    def fingerprint(self, data):
        report = audit_snapshot(data)
        self.assertIn('context_fingerprint', report)
        return report['context_fingerprint']

    def test_results_do_not_change_context(self):
        a = snapshot()
        b = snapshot([{'id':'missing'}])
        self.assertEqual(self.fingerprint(a), self.fingerprint(b))

    def test_reordering_and_explicit_all_eligible_are_equivalent(self):
        a = snapshot()
        b = copy.deepcopy(a)
        b['corpus'].reverse()
        b['queries'][0]['eligible_ids'] = ['c', 'a', 'b']
        self.assertEqual(self.fingerprint(a), self.fingerprint(b))

    def test_all_eligible_context_does_not_expand_cartesian_ids(self):
        from vector_result_audit.context import canonical_context, canonical_bytes
        data = snapshot([])
        data['corpus'] = [{'id':str(i) + 'x'*200, 'vector':[i]} for i in range(60)]
        data['queries'] = [{'id':str(i), 'vector':[0], 'eligible_ids':None, 'results':[]} for i in range(40)]
        size = len(canonical_bytes(canonical_context(validate_snapshot(data))))
        self.assertLess(size, 3*len(json.dumps(data)), 'all-eligible IDs must not expand once per query')

    def test_context_changes_and_no_vectors_in_report(self):
        a = snapshot()
        b = copy.deepcopy(a)
        b['corpus'][1]['vector'] = [2]
        self.assertNotEqual(self.fingerprint(a), self.fingerprint(b))
        b = snapshot(require_sorted=True)
        self.assertNotEqual(self.fingerprint(a), self.fingerprint(b))
        self.assertNotIn('"vector"', json.dumps(audit_snapshot(a)))
