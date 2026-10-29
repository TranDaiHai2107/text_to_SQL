from pathlib import Path
from contextlib import closing
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrieval_v3 import StructuredRAG,LiteralMasker,features,categorical_catalog,BM25,sql_structure,operator_expectations,operator_compatibility


class FakeCollection:
    def __init__(self,ids): self.ids=ids
    def query(self,**kwargs):
        return {'ids':[self.ids],'distances':[[.1+index*.01 for index in range(len(self.ids))]]}


class FakeHybrid:
    def __init__(self):
        self.examples=[
            {'id':'held','question':'How many drugs for patient 10000001?','sql':'SECRET','source':'dev'},
            {'id':'duplicate','question':'how many drugs for patient 10000001','sql':'SECRET_DUPLICATE','source':'train'},
            {'id':'other_held','question':'What was the last admission of patient 10000002?','sql':'SECRET_OTHER','source':'dev'},
            {'id':'first','question':'What were the first drugs of patient 10000003?','sql':'SELECT 1','source':'train'},
            {'id':'group','question':'How many patients per age group?','sql':'SELECT 2','source':'train'},
            {'id':'count','question':'How many drugs for patient 10000004?','sql':'SELECT 3','source':'train'},
            {'id':'null','question':'How many clinical documents are missing?','sql':'null','source':'train'},
        ]
        self.by_id={r['id']:r for r in self.examples}
        self.schema={'patients':'CREATE TABLE patients(subject_id INT)'}
        self.catalog={'height':{'id':'height','source':'d_items','column':'label','label':'height (cm)','code':'123','linksto':'chartevents'},
                      'drug':{'id':'drug','source':'prescriptions','column':'drug','label':'aspirin','code':'aspirin'}}
        self.known_values={('d_items','label'):{'height (cm)'}}
        self.lexical=BM25([r['question'] for r in self.examples])
        self.manifest={'counts':{'sql_examples_train_dev':len(self.examples)}}
        self.lock=threading.Lock()
        collection=FakeCollection(list(self.by_id))
        self.base=SimpleNamespace(query_cache={},collections={'examples':collection},examples_collection='examples',
                                  model=SimpleNamespace(encode=lambda *a,**kw:SimpleNamespace(tolist=lambda:[[1.]])))
        def retrieve(question,mode):
            self.base.query_cache[question]=[[1.]]
            return {'medical':[self.catalog['height']]}
        self.base.retrieve=retrieve


def make_rag(excluded=()):
    extra=[{'id':'cost:event_type:lab','source':'cost','column':'event_type','label':'lab','code':'lab','catalog_kind':'categorical_value'}]
    with patch('retrieval_v3.HybridRAG',FakeHybrid),patch('retrieval_v3.categorical_catalog',return_value=(extra,{('cost','event_type'):{'lab'}},[])):
        return StructuredRAG(excluded)


class RetrievalTests(unittest.TestCase):
    def test_mask_patient_date_and_clinical_literal_preserves_temporal_and_rank(self):
        masker=LiteralMasker(['aspirin','height (cm)','last recorded weight'])
        text=masker.mask('First aspirin since 2100-01-03 for patient 10000001; top 3 and 95th percentile per month')
        self.assertNotIn('10000001',text)
        self.assertNotIn('2100',text)
        self.assertNotIn('aspirin',text)
        for term in ['first','since','top','percentile','per','month']:
            self.assertIn(term,text.split())
        self.assertIn('last',masker.mask('last recorded weight').split())

    def test_structural_features_distinguish_first_last_calendar_and_aggregation(self):
        first=features('How many prescriptions before the first admission this year?')
        last=features('Average prescriptions after the last admission this month?')
        self.assertIn('aggregate:count',first)
        self.assertIn('temporal:first',first)
        self.assertIn('calendar:year',first)
        self.assertNotIn('temporal:last',first)
        self.assertIn('aggregate:average',last)
        self.assertIn('temporal:last',last)
        self.assertIn('calendar:month',last)

    def test_known_sql_ast_structures_match_question_operators(self):
        sql='SELECT subject_id, COUNT(*) FROM prescriptions GROUP BY subject_id HAVING COUNT(*) > (SELECT AVG(n) FROM (SELECT COUNT(*) n FROM prescriptions GROUP BY subject_id))'
        known=sql_structure(sql)
        self.assertTrue({'aggregate:count','aggregate:average','shape:group_by','shape:nested'}<=known)
        expected=operator_expectations('How many prescriptions per patient are above the average?')
        self.assertGreater(operator_compatibility(expected,known),operator_compatibility(expected,sql_structure('SELECT subject_id FROM patients')))
        window=sql_structure('SELECT DENSE_RANK() OVER (ORDER BY cost DESC) AS r FROM cost')
        self.assertIn('window:rank',window)
        self.assertIn('shape:window',window)

    def test_all_held_out_ids_and_exact_duplicates_filtered_from_every_pool(self):
        rag=make_rag(['held','other_held'])
        for route in ['direct','plan','structural']:
            context=rag.retrieve('How many drugs for patient 10000001?',route)
            rows=context['examples']+context['null_neighbors']
            self.assertTrue(rows)
            self.assertFalse({r['id'] for r in rows}&{'held','duplicate','other_held'})
            self.assertNotIn('SECRET',str(rows))
            self.assertEqual(context['global_exclusion_count'],3)
        self.assertEqual(rag.manifest['active_knowledge_questions'],4)

    def test_dynamic_self_exclusion_is_additional_to_global_holdout(self):
        rag=make_rag(['held'])
        context=rag.retrieve('How many drugs for patient 10000004?',exclude_id='count')
        self.assertFalse({r['id'] for r in context['examples']+context['null_neighbors']}&{'held','duplicate','count'})

    def test_excluding_every_record_returns_no_example_not_leaked_fallback(self):
        rag=make_rag(list(FakeHybrid().by_id))
        context=rag.retrieve('How many drugs?')
        self.assertEqual(context['examples'],[])
        self.assertEqual(context['null_neighbors'],[])
        self.assertEqual(context['retrieval_confidence']['example_support_count'],0)

    def test_exact_category_candidate_tied_to_table_column_and_not_exhaustive(self):
        rag=make_rag()
        context=rag.retrieve('What is the cost of lab?')
        self.assertTrue(any(r['source']=='cost' and r['column']=='event_type' and r['label']=='lab' for r in context['medical']))
        self.assertEqual(rag.known_values[('cost','event_type')],{'lab'})
        self.assertEqual(rag.known_values[('prescriptions','drug')],{'aspirin'})
        self.assertFalse(context['catalog_candidates_exhaustive'])
        self.assertEqual(context['retrieval_confidence']['kind'],'retrieval_metadata_not_probability')

    def test_unknown_holdout_id_fails_loudly(self):
        with self.assertRaises(ValueError):
            make_rag(['not_in_knowledge'])

    def test_categorical_metadata_reads_existing_columns_only(self):
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-') as folder:
            db=Path(folder)/'fixture.sqlite'
            with closing(sqlite3.connect(db)) as con:
                con.execute('CREATE TABLE cost(event_type TEXT)')
                con.executemany('INSERT INTO cost VALUES (?)',[('lab',),('procedure',),(None,)])
                con.execute('CREATE TABLE admissions(language TEXT)')
                con.execute("INSERT INTO admissions VALUES ('English')")
                con.commit()
            before=db.read_bytes()
            records,values,missing=categorical_catalog(db)
            self.assertEqual(values[('cost','event_type')],{'lab','procedure'})
            self.assertEqual(values[('admissions','language')],{'English'})
            self.assertIn('admissions.admission_type',missing)
            self.assertEqual(before,db.read_bytes())
            self.assertTrue(all(r['catalog_kind']=='categorical_value' for r in records))


if __name__=='__main__':
    unittest.main()
