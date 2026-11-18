"""Standalone regression evidence, using the same candidate audit renderer."""
from .report import document, query_html, _text, _number


def render_comparison_html(report):
    passed = report["status"] == "PASS"
    parts = ['<header><div class="eyebrow">Same context / different returned results</div>',
             '<h1>Regression evidence</h1><p>A mean score can hide a broken query. This gate checks each one.</p>',
             f'<span class="status {"pass" if passed else "fail"}">{_text(report["status"])}</span></header>',
             '<section class="summary" aria-label="Comparison summary">']
    for label, value in (("Queries", report["summary"]["query_count"]),
                         ("Recall regressions", report["summary"]["recall_regressions"]),
                         ("New findings", report["summary"]["added_findings"]),
                         ("Resolved findings", report["summary"]["resolved_findings"])):
        parts.append(f'<div><strong>{_text(value)}</strong>{label}</div>')
    parts.append('</section><section class="scope"><h2>Comparable inputs, explicit acceptance</h2>')
    parts.append(f'<p>Baseline audit <strong>{_text(report["baseline_status"])}</strong> · Candidate audit <strong>{_text(report["candidate_status"])}</strong> · Allowed per-query recall drop <strong>{_number(report["max_recall_drop"])}</strong></p>')
    parts.append(f'<p class="mono">Context SHA256: {_text(report["context_fingerprint"])}</p><ul>')
    parts.extend(f'<li>{_text(item)}</li>' for item in report["limitations"])
    parts.append('</ul></section><div class="table-wrap"><table><caption>Query-by-query change · select a query for evidence</caption><thead><tr><th>Query</th><th>Before</th><th>After</th><th>Delta</th><th>Gate</th></tr></thead><tbody>')
    for index, query in enumerate(report["queries"]):
        parts.append(f'<tr><td class="id"><a href="#query-{index}">{_text(query["id"])}</a></td><td>{_number(query["baseline_recall"])}</td><td>{_number(query["candidate_recall"])}</td><td>{_number(query["recall_delta"])}</td><td>{"Recall regression" if query["recall_regression"] else "Within drop budget"}</td></tr>')
    parts.append('</tbody></table></div><h2 class="section-heading">Candidate evidence</h2>')
    for index, query in enumerate(report["candidate_audit"]["queries"]):
        parts.append(query_html(query, index))
    parts.append('<footer>Vector Result Audit · Compare original snapshots, not unverified report summaries.')
    for key, label in (("baseline_input_sha256", "Baseline bytes SHA256"), ("candidate_input_sha256", "Candidate bytes SHA256")):
        if key in report:
            parts.append(f'<p class="mono">{label}: {_text(report[key])}</p>')
    parts.append('</footer>')
    return document("Vector Result Audit — regression evidence", ''.join(parts))
