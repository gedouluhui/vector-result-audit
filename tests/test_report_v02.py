import unittest
from html.parser import HTMLParser
from vector_result_audit import audit_snapshot
from vector_result_audit.compare import compare_snapshots
from vector_result_audit.report import render_html
from vector_result_audit.report_compare import render_comparison_html
from test_audit import snapshot


class Links(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.hrefs=[]
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k=='id':self.ids.append(v)
            if k=='href' and v.startswith('#'):self.hrefs.append(v[1:])


class ReportV02Tests(unittest.TestCase):
    def test_witness_visible_not_only_canonical_reference(self):
        report=audit_snapshot(snapshot([{'id':'b'},{'id':'c'}]))
        html=render_html(report)
        self.assertIn('Missing strictly-better neighbors',html)
        self.assertIn('1 missing',html)
        self.assertIn('Scores checked',html)
        self.assertIn('Scores missing',html)
        self.assertIn(report['context_fingerprint'],html)
        parser=Links();parser.feed(html)
        self.assertIn('query-0',parser.ids)
        self.assertIn('query-0-row-1',parser.ids)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        self.assertTrue(set(parser.hrefs)<=set(parser.ids))

    def test_comparison_shows_regression_even_when_candidate_audit_passes(self):
        r=compare_snapshots(snapshot(),snapshot([{'id':'b'},{'id':'c'}]))
        html=render_comparison_html(r)
        self.assertIn('FAIL',html);self.assertIn('-0.5',html)
        self.assertIn('Candidate audit',html);self.assertIn('PASS',html)
        self.assertIn('Missing strictly-better neighbors',html)
        self.assertIn(r['context_fingerprint'],html)
        parser=Links();parser.feed(html)
        self.assertTrue(set(parser.hrefs)<=set(parser.ids))
        self.assertEqual(len(parser.ids),len(set(parser.ids)))

    def test_comparison_escapes_ids_and_uses_no_scripts(self):
        attack='<script>alert(1)</script>'
        a=snapshot();b=snapshot([{'id':'b'},{'id':'c'}])
        for s in(a,b):s['queries'][0]['id']=attack
        html=render_comparison_html(compare_snapshots(a,b))
        self.assertNotIn(attack,html);self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script',html);self.assertNotIn('https://',html)


if __name__=='__main__':unittest.main()
