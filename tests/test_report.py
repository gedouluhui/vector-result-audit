import unittest
from test_audit import snapshot
from vector_result_audit import audit_snapshot
from vector_result_audit.report import render_html


class ReportTests(unittest.TestCase):
    def test_html_escapes_all_untrusted_ids_and_contains_real_findings(self):
        attack = '<img src=x onerror=alert(1)>'
        data = snapshot([{"id": attack}, {"id": "a"}])
        data["queries"][0]["id"] = attack
        html = render_html(audit_snapshot(data))
        self.assertNotIn(attack, html)
        self.assertIn('&lt;img', html)
        self.assertIn('unknown_id', html)
        self.assertIn('FAIL', html)
        self.assertNotIn('<script', html.lower())
        self.assertNotIn('http://', html)
        self.assertNotIn('https://', html)
        self.assertIn('name="viewport"', html)
        self.assertIn('Without min_recall', html)


if __name__ == "__main__":
    unittest.main()
