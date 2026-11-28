import unittest
from html.parser import HTMLParser
from test_audit import snapshot
from vector_result_audit import audit_snapshot
from vector_result_audit.report import render_html


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scopes = []
        self.captions = []
        self.regions = []
        self.in_caption = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "th":
            self.scopes.append(attrs.get("scope"))
        if tag == "caption":
            self.in_caption = True
            self.captions.append("")
        if tag == "div" and attrs.get("role") == "region":
            self.regions.append(attrs)

    def handle_endtag(self, tag):
        if tag == "caption":
            self.in_caption = False

    def handle_data(self, data):
        if self.in_caption:
            self.captions[-1] += data


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

    def test_evidence_table_has_scoped_headers_caption_and_keyboard_scroll_region(self):
        html = render_html(audit_snapshot(snapshot()))
        parser = TableParser()
        parser.feed(html)
        self.assertEqual(parser.scopes, ["col"] * 6)
        self.assertIn("Returned rows (2)", parser.captions[0])
        self.assertIn("zero-based", parser.captions[0])
        self.assertEqual(len(parser.regions), 1)
        self.assertEqual(parser.regions[0].get("tabindex"), "0")
        self.assertIn("Returned sequence", parser.regions[0].get("aria-label", ""))


if __name__ == "__main__":
    unittest.main()
