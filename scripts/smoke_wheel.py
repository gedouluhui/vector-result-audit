"""Install one explicit wheel into a new venv and exercise it outside the repo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def verify(wheel):
    wheel=wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='vector-audit-wheel-') as temp:
        work=Path(temp)
        envdir=work/'venv'
        venv.EnvBuilder(with_pip=True).create(envdir)
        bindir=envdir/('Scripts' if os.name=='nt' else 'bin')
        python=bindir/('python.exe' if os.name=='nt' else 'python')
        console=bindir/('vector-audit.exe' if os.name=='nt' else 'vector-audit')
        env=dict(os.environ);env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        def call(args,expected):
            p=subprocess.run(list(map(str,args)),cwd=work,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
            if p.returncode!=expected:
                raise RuntimeError(f'wheel command expected {expected}, got {p.returncode}: {p.stderr}')
            return p
        call([python,'-m','pip','install','--no-index','--no-deps',wheel],0)
        call([console,'demo','--out','demo'],0)
        passed=call([console,'check','demo/clean.json'],0)
        failed=call([python,'-m','vector_result_audit','check','demo/broken.json'],1)
        baseline=json.loads((work/'demo/clean.json').read_text())
        baseline['min_recall']=None
        (work/'before.json').write_text(json.dumps(baseline),encoding='utf-8')
        baseline['queries'][0]['results']=[{'id':'tie-east','score':1},{'id':'tie-west','score':1}]
        (work/'after.json').write_text(json.dumps(baseline),encoding='utf-8')
        changed=call([console,'compare','before.json','after.json','--html','delta.html'],1)
        report=json.loads(changed.stdout)
        if report['queries'][0]['recall_delta']!=-0.5 or not (work/'delta.html').is_file():
            raise RuntimeError('installed wheel did not produce a real comparison')
        return {'status':'PASS','wheel':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
                'isolated_venv':True,'cwd_outside_repo':True,'runtime_dependency_installation':False,
                'console_clean':json.loads(passed.stdout)['status'], 'module_broken':json.loads(failed.stdout)['status'],
                'comparison_delta':report['queries'][0]['recall_delta']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel',type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.wheel),indent=2))
