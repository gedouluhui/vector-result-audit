"""Generate the public synthetic report from the actual comparison implementation."""
import argparse
import copy
from pathlib import Path
import sys
from vector_result_audit import compare_snapshots
from vector_result_audit.cli import demo_snapshots
from vector_result_audit.output import atomic_write
from vector_result_audit.report_compare import render_comparison_html


def build():
    before=demo_snapshots()['clean']
    before['queries'][0]['id']='synthetic-tie-regression'
    after=copy.deepcopy(before)
    after['queries'][0]['results']=[{'id':'tie-east','score':1},{'id':'tie-west','score':1}]
    report=compare_snapshots(before,after)
    if report['baseline_status']!='PASS' or report['status']!='FAIL' or report['queries'][0]['recall_delta']!=-0.5:
        raise RuntimeError('public demo no longer demonstrates the intended actual regression')
    banner=('<aside class="scope"><strong>Synthetic example · Vector Result Audit</strong>'
            '<p>This is a generated, fixed example of a deliberately broken export, not a live database result. '
            'The CLI and Python API run locally, with no runtime dependencies or API keys.</p>'
            '<p><a href="https://github.com/gedouluhui/vector-result-audit">Source and quickstart</a> · '
            '<a href="https://github.com/gedouluhui/vector-result-audit/releases">Download releases</a> · '
            '<a href="https://github.com/gedouluhui/vector-result-audit/blob/main/docs/contract.md">Contract and limits</a></p></aside>')
    return render_comparison_html(report).replace('<main>','<main>'+banner,1)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--check',action='store_true',help='verify existing bytes without changing them')
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args(argv)
    try:
        content=build()
        if args.check:
            if args.out.read_bytes()!=content.encode('utf-8'):
                raise RuntimeError('public demo differs from current implementation; regenerate explicitly')
        else:
            atomic_write(args.out,content,args.force)
        return 0
    except (OSError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
