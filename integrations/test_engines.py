"""Mandatory optional-integration suite: missing engines are ERROR, never skip."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import faiss
import numpy as np
from qdrant_client import QdrantClient, models

from vector_result_audit import audit_snapshot, compare_snapshots
from vector_result_audit.adapters import faiss_rows, qdrant_rows, attach_results


def base_case(metric):
    return {'schema_version':1, 'metric':metric, 'k':3, 'min_recall':1.0,
            'score_kind':{'l2':'squared_l2','inner_product':'dot','cosine':'cosine_similarity'}[metric],
            'require_scores':True, 'require_sorted':True, 'allow_null_padding':True,
            'score_atol':1e-6, 'score_rtol':1e-6,
            'corpus':[{'id':'a','vector':[1,0]}, {'id':'b','vector':[1,2]},
                      {'id':'c','vector':[-2,1]}, {'id':'d','vector':[3,4]}],
            'queries':[{'id':'q','vector':[1,0.25],'eligible_ids':None,'results':[]}]}


def faiss_capture(metric,k=3):
    data=base_case(metric);data['k']=k
    x=np.array([item['vector'] for item in data['corpus']],dtype='float32')
    q=np.array([data['queries'][0]['vector']],dtype='float32')
    if metric=='cosine':faiss.normalize_L2(x);faiss.normalize_L2(q)
    index=faiss.IndexFlatL2(2) if metric=='l2' else faiss.IndexFlatIP(2)
    index.add(x)
    distances,labels=index.search(q,k)
    return attach_results(data,faiss_rows(labels,distances,id_map={i:item['id'] for i,item in enumerate(data['corpus'])}))


def qdrant_capture(metric,apply_filter=True):
    data=base_case(metric)
    if metric=='l2':data['score_kind']='l2'
    allowed=[item['id'] for i,item in enumerate(data['corpus']) if i!=0]
    data['queries'][0]['eligible_ids']=allowed
    client=QdrantClient(':memory:')
    try:
        client.create_collection('synthetic', vectors_config=models.VectorParams(size=2,distance={
            'l2':models.Distance.EUCLID,'inner_product':models.Distance.DOT,'cosine':models.Distance.COSINE}[metric]))
        client.upsert('synthetic', points=[models.PointStruct(id=i,vector=list(map(float,item['vector'])),payload={'allowed':i!=0}) for i,item in enumerate(data['corpus'])])
        filtering=models.Filter(must=[models.FieldCondition(key='allowed',match=models.MatchValue(value=True))])
        response=client.query_points('synthetic',query=data['queries'][0]['vector'],
                                     query_filter=filtering if apply_filter else None,limit=data['k'])
        rows=qdrant_rows(response.points,id_map={i:item['id'] for i,item in enumerate(data['corpus'])})
        return attach_results(data,[rows])
    finally:client.close()


class RealEngineTests(unittest.TestCase):
    def test_faiss_all_metrics(self):
        for metric in ('l2','inner_product','cosine'):
            with self.subTest(metric=metric):
                report=audit_snapshot(faiss_capture(metric))
                self.assertEqual(report['status'],'PASS',report['queries'][0]['findings'])
                self.assertEqual(report['queries'][0]['recall'],1.0)
                self.assertEqual(report['coverage']['score_checked_rows'],3)

    def test_qdrant_local_all_metrics_and_filter(self):
        for metric in ('l2','inner_product','cosine'):
            with self.subTest(metric=metric):
                data=qdrant_capture(metric)
                self.assertNotIn('a',[r['id'] for r in data['queries'][0]['results']])
                report=audit_snapshot(data)
                self.assertEqual(report['status'],'PASS',report['queries'][0]['findings'])
                self.assertEqual(report['queries'][0]['recall'],1.0)

    def test_faiss_real_sentinel_preserves_requested_slots(self):
        data=faiss_capture('l2',k=6)
        self.assertEqual(data['queries'][0]['results'][-2:],[{'id':None,'score':None}]*2)
        self.assertEqual(audit_snapshot(data)['status'],'PASS')

    def test_wrong_score_encoding_is_detected_from_real_faiss(self):
        data=faiss_capture('l2');data['score_kind']='l2'
        report=audit_snapshot(data)
        self.assertEqual(report['status'],'FAIL')
        self.assertIn('score_mismatch',{f['code'] for f in report['queries'][0]['findings']})

    def test_missing_filter_in_real_query_is_detected(self):
        good=qdrant_capture('l2',True);bad=qdrant_capture('l2',False)
        r=compare_snapshots(good,bad)
        self.assertEqual(r['status'],'FAIL')
        self.assertIn('ineligible_id',{f['code'] for f in r['candidate_audit']['queries'][0]['findings']})

    def test_reversed_real_results_have_full_recall_but_wrong_order(self):
        good=faiss_capture('inner_product');bad=copy.deepcopy(good)
        bad['queries'][0]['results'].reverse()
        r=compare_snapshots(good,bad)
        self.assertEqual(r['queries'][0]['recall_delta'],0)
        self.assertEqual(r['status'],'FAIL')
        self.assertIn('out_of_order',{f['code'] for f in r['candidate_audit']['queries'][0]['findings']})

    def test_example_runs_both_engines_and_writes_true_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'capture'
            p=subprocess.run([sys.executable,'-m','examples.engine_capture','--out',str(out)],
                             capture_output=True,text=True,timeout=90)
            self.assertEqual(p.returncode,0,p.stderr)
            receipt=json.loads((out/'receipt.json').read_text())
            self.assertEqual(set(receipt['engines']),{'faiss','qdrant-local'})
            for engine in ('faiss','qdrant-local'):
                base=json.loads((out/engine/'baseline.json').read_text())
                candidate=json.loads((out/engine/'candidate.json').read_text())
                compare=json.loads((out/engine/'comparison.json').read_text())
                self.assertEqual(audit_snapshot(base)['status'],'PASS')
                self.assertEqual(compare_snapshots(base,candidate),compare)
                self.assertEqual(compare['status'],'FAIL')
                self.assertTrue((out/engine/'comparison.html').is_file())
            again=subprocess.run([sys.executable,'-m','examples.engine_capture','--out',str(out)],capture_output=True)
            self.assertEqual(again.returncode,2)


if __name__=='__main__':unittest.main()
