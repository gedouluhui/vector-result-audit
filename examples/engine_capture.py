"""Run real, ephemeral retrieval libraries on synthetic data and export evidence.

The candidate failures are intentionally injected application/export mistakes,
not evidence of upstream engine defects. No server connection or model download.
"""
import argparse
import copy
from importlib.metadata import version
import json
from pathlib import Path
import sys

from vector_result_audit import audit_snapshot, compare_snapshots
from vector_result_audit.adapters import faiss_rows, qdrant_rows, attach_results
from vector_result_audit.output import atomic_write
from vector_result_audit.report import render_html
from vector_result_audit.report_compare import render_comparison_html


def _dump(data):
    return json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False) + '\n'


def template(kind):
    return {'schema_version':1, 'metric':'l2', 'score_kind':kind, 'k':2,
            'require_scores':True, 'require_sorted':True, 'min_recall':1.0,
            'corpus':[{'id':'doc-0','vector':[0,0]}, {'id':'doc-1','vector':[3,4]}, {'id':'doc-2','vector':[6,8]}],
            'queries':[{'id':'synthetic-distance-query','vector':[0,0], 'eligible_ids':None, 'results':[]}]}


def capture_faiss():
    import faiss
    import numpy as np
    data=template('squared_l2')
    x=np.array([p['vector'] for p in data['corpus']],dtype='float32')
    index=faiss.IndexFlatL2(2)
    index.add(x)
    scores,labels=index.search(np.array([[0,0]],dtype='float32'),2)
    base=attach_results(data,faiss_rows(labels,scores,id_map={i:p['id'] for i,p in enumerate(data['corpus'])}))
    bad=copy.deepcopy(base)
    bad['queries'][0]['results'][0]=copy.deepcopy(bad['queries'][0]['results'][1])
    return base,bad,'Injected export defect: duplicate the second result, losing the closest neighbor.'


def capture_qdrant():
    from qdrant_client import QdrantClient, models
    data=template('l2')
    data['queries'][0]['eligible_ids']=['doc-1','doc-2']
    ids={i:p['id'] for i,p in enumerate(data['corpus'])}
    client=QdrantClient(':memory:')
    try:
        client.create_collection('synthetic',vectors_config=models.VectorParams(size=2,distance=models.Distance.EUCLID))
        client.upsert('synthetic',points=[models.PointStruct(id=i,vector=list(map(float,p['vector'])),payload={'allowed':i>0}) for i,p in enumerate(data['corpus'])])
        filt=models.Filter(must=[models.FieldCondition(key='allowed',match=models.MatchValue(value=True))])
        good=client.query_points('synthetic',query=[0.0,0.0],query_filter=filt,limit=2)
        bad=client.query_points('synthetic',query=[0.0,0.0],limit=2)
        return (attach_results(data,[qdrant_rows(good.points,id_map=ids)]),
                attach_results(data,[qdrant_rows(bad.points,id_map=ids)]),
                'Injected application defect: omit the requested eligibility filter in the candidate query.')
    finally:
        client.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path,help='new directory only')
    parser.add_argument('--engine',choices=['all','faiss','qdrant'],default='all')
    args=parser.parse_args(argv)
    try:
        # Fail missing dependencies before creating outputs. These are real integrations.
        selected=[]
        if args.engine in ('all','faiss'):
            selected.append(('faiss',capture_faiss,'faiss-cpu'))
        if args.engine in ('all','qdrant'):
            selected.append(('qdrant-local',capture_qdrant,'qdrant-client'))
        versions={package:version(package) for _,_,package in selected}
        versions['numpy']=version('numpy')
        args.out.mkdir(parents=False,exist_ok=False)
        receipts={}
        for name, capture, package in selected:
            folder=args.out/name;folder.mkdir()
            base,bad,injection=capture()
            base_report=audit_snapshot(base); bad_report=audit_snapshot(bad)
            comparison=compare_snapshots(base,bad)
            for filename,data in [('baseline.json',base),('candidate.json',bad),
                                  ('baseline.report.json',base_report),('candidate.report.json',bad_report),
                                  ('comparison.json',comparison)]:
                atomic_write(folder/filename,_dump(data))
            atomic_write(folder/'baseline.html',render_html(base_report))
            atomic_write(folder/'candidate.html',render_html(bad_report))
            atomic_write(folder/'comparison.html',render_comparison_html(comparison))
            receipts[name]={'baseline':base_report['status'],'candidate':bad_report['status'],
                            'comparison':comparison['status'],'injection':injection,'library_version':versions[package]}
            if base_report['status']!='PASS' or bad_report['status']!='FAIL' or comparison['status']!='FAIL':
                raise RuntimeError('real engine control did not behave as expected: '+name)
        receipt={'status':'CONTROLS_VERIFIED','synthetic':True,'versions':versions,'engines':receipts,
                 'scope':'Faiss CPU IndexFlat and Qdrant client local memory mode; not server/ANN performance certification.'}
        atomic_write(args.out/'receipt.json',_dump(receipt))
        print(_dump(receipt),end='')
        return 0
    except (OSError,ImportError,RuntimeError) as exc:
        print(_dump({'status':'ERROR','error':str(exc)}),file=sys.stderr,end='')
        return 2


if __name__=='__main__':raise SystemExit(main())
