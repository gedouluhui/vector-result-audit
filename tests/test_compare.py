import copy
import unittest
from vector_result_audit import InputError
from vector_result_audit.compare import compare_snapshots
from test_audit import snapshot


class ComparisonTests(unittest.TestCase):
    def test_recall_regression_and_exact_allowed_drop(self):
        before, after = snapshot(), snapshot([{'id':'b'}, {'id':'c'}])
        r = compare_snapshots(before, after)
        self.assertEqual(r['status'], 'FAIL')
        self.assertEqual(r['queries'][0]['recall_delta'], -0.5)
        self.assertEqual(r['queries'][0]['recall_regression'], True)
        self.assertEqual(r['baseline_status'], 'PASS')
        self.assertEqual(r['candidate_status'], 'PASS')
        self.assertEqual(compare_snapshots(before, after, max_recall_drop=0.5)['status'], 'PASS')

    def test_candidate_contract_failure_cannot_be_waived(self):
        a = snapshot([{'id':'a'}, {'id':'a'}])
        r = compare_snapshots(a, a, max_recall_drop=1)
        self.assertEqual(r['status'], 'FAIL')
        self.assertEqual(r['candidate_status'], 'FAIL')

    def test_tie_alternative_and_context_reordering(self):
        a = snapshot()
        b = snapshot([{'id':'a'}, {'id':'c'}])
        b['corpus'].reverse()
        b['queries'][0]['eligible_ids'] = ['b','a','c']
        r = compare_snapshots(a, b)
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual(r['queries'][0]['recall_delta'], 0)
        self.assertEqual(r['queries'][0]['added_findings'], [])

    def test_refuses_all_incomparable_categories(self):
        a = snapshot()
        changes = [lambda b:b.update(k=1), lambda b:b.update(require_sorted=True),
                   lambda b:b.update(score_atol=0.1), lambda b:b.update(min_recall=1),
                   lambda b:b['corpus'][0].update(vector=[2]),
                   lambda b:b['queries'][0].update(vector=[2]),
                   lambda b:b['queries'][0].update(eligible_ids=['a']),
                   lambda b:b['queries'][0].update(id='different')]
        for mutate in changes:
            b = copy.deepcopy(a); mutate(b)
            with self.subTest(change=changes.index(mutate)), self.assertRaisesRegex(InputError, 'incomparable'):
                compare_snapshots(a,b)

    def test_corpus_change_refused_before_diff(self):
        before = snapshot()
        after = snapshot()
        after['corpus'][0]['vector'] = [2]
        with self.assertRaisesRegex(InputError, 'incomparable corpus'):
            compare_snapshots(before, after)

    def test_query_alignment_is_by_identity_not_position(self):
        a = snapshot()
        a['queries'].append({**copy.deepcopy(a['queries'][0]), 'id':'other'})
        b = copy.deepcopy(a); b['queries'].reverse()
        b['queries'][0]['results'] = [{'id':'b'}, {'id':'c'}]
        r = compare_snapshots(a,b)
        self.assertEqual({q['id']:q['recall_delta'] for q in r['queries']}, {'q':0.0,'other':-0.5})
        self.assertEqual(r['status'], 'FAIL')

    def test_mean_improvement_cannot_hide_one_query_regression(self):
        a = snapshot([{'id':'b'}, {'id':'c'}])
        a['queries'].append({'id':'second','vector':[0], 'eligible_ids':None, 'results':[{'id':'a'},{'id':'b'}]})
        b = copy.deepcopy(a)
        b['queries'][0]['results'] = [{'id':'a'},{'id':'b'}]
        b['queries'][1]['results'] = [{'id':'b'},{'id':'c'}]
        r = compare_snapshots(a,b)
        self.assertEqual(r['status'],'FAIL')
        self.assertEqual(r['summary']['recall_regressions'],1)

    def test_added_resolved_findings_and_empty_eligible(self):
        a = snapshot([{'id':'missing'}, {'id':'a'}])
        b = snapshot()
        r = compare_snapshots(a,b)
        self.assertIn('unknown_id', [f['code'] for f in r['queries'][0]['resolved_findings']])
        self.assertEqual(r['queries'][0]['added_findings'], [])
        self.assertEqual(r['status'],'PASS')
        a = snapshot([]); a['queries'][0]['eligible_ids']=[]
        r = compare_snapshots(a,a)
        self.assertIsNone(r['queries'][0]['recall_delta'])
        self.assertFalse(r['queries'][0]['recall_regression'])

    def test_bad_threshold_budget_input_immutability(self):
        a = snapshot(); old=copy.deepcopy(a)
        for value in (True,-1,1.01,float('nan'),float('inf'),'0'):
            with self.subTest(value=value), self.assertRaises(InputError):
                compare_snapshots(a,a,max_recall_drop=value)
        with self.assertRaises(InputError):compare_snapshots(a,a,max_work=1)
        compare_snapshots(a,a)
        self.assertEqual(a,old)
