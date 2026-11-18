"""Standalone evidence ledger. Input strings are text, never markup or code."""
from html import escape

STYLE = """
:root{color-scheme:light;--ink:#14263a;--muted:#4f6275;--line:#cfdae5;--paper:#f1f6fb;--navy:#142f49;--blue:#2365b0;--red:#9d303b;--green:#116a5e}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 'Segoe UI',Arial,sans-serif}
main{max-width:1180px;margin:auto;padding:48px 28px}header{border-left:5px solid var(--blue);padding:6px 0 12px 24px;margin-bottom:32px}
h1,h2{font-family:Bahnschrift,'Segoe UI',sans-serif;line-height:1.15;letter-spacing:-.035em}h1{font-size:clamp(32px,5vw,52px);margin:12px 0}h2{font-size:25px;margin:0}
p{margin:10px 0}.eyebrow{font:12px/1.5 Consolas,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
code,.mono{font-family:Consolas,'Courier New',monospace;font-size:.88em;overflow-wrap:anywhere}.status{font-weight:700;letter-spacing:.06em;padding:6px 12px;border:1px solid currentColor;display:inline-block}
.pass{color:var(--green);background:#effaf6}.fail{color:var(--red);background:#fff4f3}.summary{display:flex;gap:24px;flex-wrap:wrap;border-block:1px solid var(--line);padding:18px 0;margin-bottom:26px}.summary strong{font-size:24px;font-variant-numeric:tabular-nums;display:block}
.scope{border:1px solid var(--line);background:#fff;padding:20px 24px;margin-bottom:28px}.scope ul{padding-left:20px;margin-bottom:0}.scope li{margin-top:7px;color:var(--muted)}
.query{background:white;border:1px solid var(--line);margin:22px 0;padding:25px}.query-top{display:flex;justify-content:space-between;gap:20px;align-items:start}.query-title{overflow-wrap:anywhere;min-width:0}
.metrics{font-size:14px;color:var(--muted);margin:14px 0}.metrics strong{color:var(--ink)}.findings{padding:0;list-style:none}.findings li{border-left:3px solid var(--red);background:#fff7f6;padding:10px 14px;margin:10px 0;overflow-wrap:anywhere}.findings code{color:var(--red);font-weight:700}.ok{color:var(--green)}
.table-wrap{overflow:auto;border:1px solid var(--line);margin-top:20px}table{border-collapse:collapse;width:100%;font-size:13px;min-width:640px}caption{text-align:left;padding:12px 14px;font-weight:600;background:#f5f8fc}
th{background:#e9f0f7;text-align:left;color:var(--navy);font-weight:600}td,th{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}td.id{max-width:250px;overflow-wrap:anywhere}tr:last-child td{border-bottom:0}.note,footer{font-size:13px;color:var(--muted)}footer{margin-top:30px;overflow-wrap:anywhere}details{margin-top:16px}summary{cursor:pointer;font-weight:600}summary:focus-visible{outline:3px solid var(--blue);outline-offset:4px}
a{color:#155699;text-decoration-thickness:1px;text-underline-offset:3px}a:focus-visible{outline:3px solid var(--blue);outline-offset:4px}.section-heading{margin-top:36px}.witness{background:#fff9e9;border-left:3px solid #916614;padding:12px 16px;margin:16px 0;overflow-wrap:anywhere}.witness ul{margin:6px 0;padding-left:20px}.jump{display:flex;flex-wrap:wrap;gap:8px 18px;margin:20px 0;font-size:14px}article{scroll-margin-top:16px}
@media(max-width:600px){main{padding:24px 14px}header{padding-left:16px}.query{padding:18px 14px}.query-top{flex-direction:column;gap:8px}.scope{padding:16px}.summary{gap:18px}}
@media print{body{background:white}main{padding:0;max-width:none}.query{break-inside:auto}.table-wrap{overflow:visible}table{min-width:0}details>*{display:block}}
"""


def _text(value):
    return escape(str(value), quote=True)


def _number(value):
    return "N/A" if value is None else _text(repr(value))


def document(title, body):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            f'<title>{_text(title)}</title><style>{STYLE}</style></head><body><main>{body}</main></body></html>')


def query_html(q, index):
    anchor = f"query-{index}"
    parts = [f'<article id="{anchor}" class="query"><div class="query-top"><div class="query-title"><div class="eyebrow">Query</div>',
             f'<h2>{_text(q["id"])}</h2></div><span class="mono">{q["hits"]} credited / {q["effective_k"]} available top-k</span></div>',
             f'<p class="metrics">Recall <strong>{_number(q["recall"])}</strong> · Precision <strong>{_number(q["precision"])}</strong> · Eligible <strong>{q["eligible_count"]}</strong> · Boundary distance <strong>{_number(q["boundary_distance"])}</strong> · Boundary gap (rank) <strong>{_number(q["boundary_gap"])}</strong></p>',
             f'<p class="metrics">Scores checked <strong>{q["score_checked_rows"]}</strong> · Scores missing <strong>{q["score_missing_rows"]}</strong></p>']
    if q["missing_strict_count"]:
        parts.append(f'<section class="witness"><strong>Missing strictly-better neighbors</strong><p>{q["missing_strict_count"]} missing · showing {len(q["missing_strict_witnesses"])} examples, not arbitrary boundary ties</p><ul>')
        for item in q["missing_strict_witnesses"]:
            parts.append(f'<li><code>{_text(item["id"])}</code> — distance {_number(item["distance"])} · rank {_number(item["rank_value"])}</li>')
        parts.append('</ul></section>')
    if q["findings"]:
        parts.append('<ul class="findings">')
        for finding in q["findings"]:
            position = 'query' if finding["row"] is None else f'row {finding["row"]}'
            target = anchor if finding["row"] is None else f'{anchor}-row-{finding["row"]}'
            parts.append(f'<li><code>{_text(finding["code"])}</code> · <a href="#{target}">{_text(position)}</a><br>{_text(finding["detail"])}</li>')
        parts.append('</ul>')
    else:
        parts.append('<p class="ok">No violations of the declared checks.</p>')
    if q["observations"]:
        parts.append('<p class="note">Observations: ' + ', '.join(_text(x) for x in q["observations"]) + '</p>')
    parts.append('<div class="table-wrap"><table><caption>Returned sequence — original zero-based row positions; smaller rank is better</caption><thead><tr><th>Row</th><th>ID</th><th>Distance / rank</th><th>Observed score</th><th>Score residual</th><th>Eligible / within k</th></tr></thead><tbody>')
    for row in q["rows"]:
        parts.append(f'<tr id="{anchor}-row-{row["row"]}"><td>{row["row"]}</td><td class="id mono">{_text(row["id"])}</td><td class="mono">{_number(row["reference_distance"])} / {_number(row["rank_value"])}</td><td class="mono">{_number(row["score"])}</td><td class="mono">{_number(row["score_error"])}</td><td>{"yes" if row["eligible"] else "no"} / {"yes" if row["within_k"] else "no"}</td></tr>')
    if not q["rows"]:
        parts.append('<tr><td colspan="6">No returned rows. Empty eligibility is N/A, not perfect recall.</td></tr>')
    parts.append('</tbody></table></div><details><summary>Canonical reference and tie credit</summary>')
    parts.append(f'<p>{q["strict_hits"]} strictly-better hits + {q["boundary_hits"]} boundary hits. Alternative exact boundary ties are valid; they cannot replace a missing strictly-better neighbor.</p>')
    parts.append('<p class="mono">' + '; '.join(f'{_text(item["id"])}: distance {_number(item["distance"])} / rank {_number(item["rank_value"])}' for item in q["reference_top_k"]) + '</p></details></article>')
    return ''.join(parts)


def render_html(report):
    summary = report["summary"]
    passed = report["status"] == "PASS"
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
             '<title>Vector Result Audit — evidence ledger</title><style>', STYLE, '</style></head><body><main>',
             '<header><div class="eyebrow">Offline retrieval / result contract</div>',
             '<h1>Vector Result Audit</h1><p>Inspect what came back. Keep approximation separate from protocol errors.</p>',
             f'<span class="status {"pass" if passed else "fail"}">{_text(report["status"])}</span></header>',
             '<section class="summary" aria-label="Audit summary">']
    for label, value in (("Queries", summary["query_count"]), ("Contract violations", summary["contract_violations"]),
                         ("Recall budget failures", summary["recall_budget_failures"]), ("Mean recall", _number(summary["mean_recall"]))):
        parts.append(f'<div><strong>{_text(value)}</strong>{label}</div>')
    parts.append('</section><section class="scope"><h2>What this verdict covers</h2>')
    parts.append(f'<p>Metric <code>{_text(report["metric"])}</code> · Score encoding <code>{_text(report["score_kind"])}</code> · Minimum recall <code>{_number(report["coverage"]["recall_threshold"])}</code></p>')
    parts.append(f'<p class="metrics">Require scores: {_text(report["coverage"]["require_scores"])} · Require sorted: {_text(report["coverage"]["require_sorted"])}</p>')
    parts.append(f'<p class="mono">Context SHA256: {_text(report["context_fingerprint"])}</p>')
    parts.append(f'<p class="mono">{_text(report["rank_policy"])}</p><ul>')
    parts.extend(f'<li>{_text(item)}</li>' for item in report["coverage"]["limitations"])
    parts.append('</ul></section>')
    parts.append('<nav class="jump" aria-label="Query evidence">' + ''.join(f'<a href="#query-{i}">{_text(q["id"])}</a>' for i,q in enumerate(report["queries"])) + '</nav>')
    for i, q in enumerate(report["queries"]):
        parts.append(query_html(q, i))
    parts.append(f'<footer>Vector Result Audit {_text(report["tool_version"])} · Offline report · No remote assets or scripts')
    if report.get("input_sha256"):
        parts.append(f'<p class="mono">Input SHA256: {_text(report["input_sha256"])}</p>')
    parts.append('</footer></main></body></html>')
    return ''.join(parts)
