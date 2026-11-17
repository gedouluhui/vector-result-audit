import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_audit import snapshot
from vector_result_audit import audit_snapshot, InputError
from vector_result_audit.report import render_html
from vector_result_audit.schema import validate_snapshot


class ReviewRegressions(unittest.TestCase):
    def test_cumulative_results_budget_not_scalar_only(self):
        data = snapshot(k=10000)
        q = data['queries'][0]
        q['results'] = [{'id': 'a'}] * 5000
        data['queries'] = [q, {**copy.deepcopy(q), 'id': 'q2'}]
        self.assertEqual(len(validate_snapshot(data)['queries']), 2)
        data['queries'][1]['results'].append({'id': 'a'})
        with self.assertRaisesRegex(InputError, 'total result rows'):
            validate_snapshot(data)

    def test_reference_evidence_budget_before_materialization(self):
        data = snapshot(k=200)
        data['corpus'] = [{'id': str(i), 'vector': [i]} for i in range(200)]
        data['queries'] = [{'id': str(i), 'vector': [0], 'eligible_ids': None, 'results': []} for i in range(100)]
        with self.assertRaisesRegex(InputError, 'evidence rows'):
            validate_snapshot(data)
        data['queries'] = data['queries'][:99]
        self.assertEqual(len(validate_snapshot(data)['queries']), 99)

    def test_all_finite_binary64_scores_become_evidence(self):
        for score in (1e301, sys.float_info.max, -sys.float_info.max):
            data = snapshot([{'id': 'a', 'score': score}], k=1, score_kind='l2')
            report = audit_snapshot(data)
            self.assertEqual(report['status'], 'FAIL')
            self.assertIn('score_mismatch', [f['code'] for f in report['queries'][0]['findings']])
            json.dumps(report, allow_nan=False)

    def test_large_finite_score_cli_is_fail_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'large.json'
            path.write_text(json.dumps(snapshot([{'id': 'a', 'score': 1e301}], k=1, score_kind='l2')), encoding='utf-8')
            p = subprocess.run([sys.executable, '-m', 'vector_result_audit', 'check', str(path)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout)
            self.assertEqual(json.loads(p.stdout)['status'], 'FAIL')

    def test_html_distinguishes_near_tie_and_displays_gap(self):
        data = snapshot([{'id': 'b'}], k=1, min_recall=1)
        data['corpus'] = [{'id': 'a', 'vector': [1]}, {'id': 'b', 'vector': [1.000000001]}]
        report = audit_snapshot(data)
        self.assertEqual(report['queries'][0]['recall'], 0.0)
        html = render_html(report)
        self.assertIn('1.000000001', html)
        self.assertIn('Boundary gap', html)
        self.assertIn(repr(report['queries'][0]['boundary_gap']), html)
