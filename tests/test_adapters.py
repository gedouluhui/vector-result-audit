import copy
import unittest
from types import SimpleNamespace
from vector_result_audit import InputError, audit_snapshot
from vector_result_audit.adapters import faiss_rows, qdrant_rows, attach_results
from test_audit import snapshot


class AdapterTests(unittest.TestCase):
    def test_faiss_preserves_positions_duplicates_and_padding(self):
        rows = faiss_rows([[4,-1,4]], [[25,3.4e38,25]], id_map={4:'doc'})
        self.assertEqual(rows,[[{'id':'doc','score':25.0},{'id':None,'score':None},{'id':'doc','score':25.0}]])
        self.assertEqual(faiss_rows([[]],[[]],id_map={0:'doc'}),[[]])

    def test_faiss_shape_and_label_errors_not_silently_filtered(self):
        cases = [([0],[0]), ([[0,0]], [[1]]), ([[0],[0]],[[1]]),
                 ([[2]],[[1]]), ([[-2]],[[1]]), ([[True]],[[1]]), ([[0.0]],[[1]]),
                 ([[0]],[[float('nan')]]), ([[0]],[[True]])]
        for labels,scores in cases:
            with self.subTest(labels=labels), self.assertRaises(InputError):
                faiss_rows(labels,scores,id_map={0:'a'})

    def test_mapping_does_not_conflate_string_and_integer_provider_ids(self):
        points=[SimpleNamespace(id=1,score=1), {'id':'1','score':2,'payload':{'ignored':True}}]
        self.assertEqual(qdrant_rows(points,id_map={1:'integer','1':'string'}),
                         [{'id':'integer','score':1.0},{'id':'string','score':2.0}])
        with self.assertRaises(InputError):qdrant_rows([{'id':True,'score':1}],id_map={1:'one'})

    def test_qdrant_invalid_or_unmapped_results_rejected(self):
        for points in ([{'id':2,'score':1}], [{'id':1}], [{'id':1,'score':None}],
                       [{'id':1,'score':float('inf')}], [object()]):
            with self.subTest(points=points), self.assertRaises(InputError):
                qdrant_rows(points,id_map={1:'one'})
        with self.assertRaises(InputError):qdrant_rows(iter([]),id_map={1:'one'})

    def test_maps_are_one_to_one_and_typed(self):
        for mapping in ({True:'a'}, {1:'a',2:'a'}, {1:''}, {1:23}, {-1:'bad'}):
            with self.subTest(mapping=mapping), self.assertRaises(InputError):
                faiss_rows([[1]],[[1]],id_map=mapping)
        with self.assertRaises(InputError):faiss_rows([[1]],[[1]],id_map={'1':'a'})

    def test_attach_requires_all_queries_and_is_immutable(self):
        data=snapshot(score_kind='l2')
        old=copy.deepcopy(data)
        r=attach_results(data,[[{'id':'a','score':0},{'id':'b','score':1}]])
        self.assertEqual(audit_snapshot(r)['status'],'PASS')
        self.assertEqual(data,old)
        with self.assertRaises(InputError):attach_results(data,[])
        with self.assertRaises(InputError):attach_results(data,[[],[]])

    def test_array_budget_checked_before_tolist(self):
        class TooBig:
            shape=(1,10001)
            def tolist(self):
                raise AssertionError('must reject shape before materialization')
        with self.assertRaisesRegex(InputError,'rows'):
            faiss_rows(TooBig(),TooBig(),id_map={0:'a'})

    def test_list_result_budget_and_ragged_shape(self):
        with self.assertRaises(InputError):
            faiss_rows([[0]*5001,[0]*5001],[[1]*5001,[1]*5001],id_map={0:'a'})
        with self.assertRaises(InputError):
            faiss_rows([[0],[0,0]],[[1],[1,1]],id_map={0:'a'})
        with self.assertRaises(InputError):
            qdrant_rows([{'id':1,'score':1}]*10001,id_map={1:'a'})
