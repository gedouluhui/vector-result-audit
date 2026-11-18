"""Exercise public CLI with real PASS/FAIL/ERROR outcomes and retain artifacts."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def write_json(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=True,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def run(out):
    out.mkdir(parents=False,exist_ok=False)
    baseline={'schema_version':1,'metric':'l2','k':2,'min_recall':1.0,
              'corpus':[{'id':'closest','vector':[0]},{'id':'tie-left','vector':[-1]},{'id':'tie-right','vector':[1]}],
              'queries':[{'id':'synthetic-tie-trap','vector':[0],'eligible_ids':None,
                          'results':[{'id':'closest'},{'id':'tie-left'}]}]}
    candidate=copy.deepcopy(baseline)
    candidate['queries'][0]['results']=[{'id':'tie-left'},{'id':'tie-right'}]
    changed=copy.deepcopy(candidate);changed['corpus'][0]['vector']=[10]
    for name,data in (('baseline',baseline),('candidate',candidate),('changed',changed)):
        write_json(out/(name+'.input.json'),data)
    commands=[('baseline',['check',str(out/'baseline.input.json')],0),
              ('candidate',['check',str(out/'candidate.input.json')],1),
              ('comparison',['compare',str(out/'baseline.input.json'),str(out/'candidate.input.json')],1),
              ('incomparable',['compare',str(out/'baseline.input.json'),str(out/'changed.input.json')],2)]
    receipts={}
    for name,args,expected in commands:
        if name!='incomparable':args += ['--json',str(out/(name+'.json')),'--html',str(out/(name+'.html'))]
        p=subprocess.run([sys.executable,'-m','vector_result_audit',*args],cwd=ROOT,
                         env=dict(os.environ,PYTHONPATH=str(ROOT)),capture_output=True,text=True,encoding='utf-8',timeout=30)
        (out/(name+'.stdout.json')).write_text(p.stdout,encoding='utf-8',newline='\n')
        (out/(name+'.stderr.txt')).write_text(p.stderr,encoding='utf-8',newline='\n')
        receipts[name]=p.returncode
        write_json(out/'receipt.json',{'synthetic':True,'exit_codes':receipts})
        if p.returncode!=expected:
            raise RuntimeError(f'{name}: expected exit {expected}, got {p.returncode}; inspect retained evidence')
        parsed=json.loads(p.stdout)
        status='PASS' if expected==0 else 'FAIL' if expected==1 else 'ERROR'
        if parsed['status']!=status:
            raise RuntimeError(f'{name}: verdict does not match exit code')
    return receipts


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        print(json.dumps({'status':'CONTROLS_VERIFIED','exit_codes':run(args.out.resolve())},indent=2))
    except (OSError,ValueError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(1)
