import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_deepseek import configurations,frozen_config,save_rows,OUR_PRIMARY


class ComparisonTests(unittest.TestCase):
    def test_common_backbone_and_knowledge_are_explicit(self):
        ours,vanna=configurations('unit',{'counts':{}},{'counts':{}},8)
        for key in ['provider','model','thinking','temperature','seed','knowledge_splits','knowledge_questions','max_sql_completion_tokens']:
            self.assertEqual(ours[key],vanna[key])
        self.assertEqual(ours['knowledge_splits'],['train','dev'])
        self.assertFalse(ours['gold_test_access_during_inference'])
        self.assertIsNone(ours['seed'])
        self.assertEqual(ours['primary_variant'],OUR_PRIMARY)
        self.assertEqual(vanna['primary_variant'],'vanna')

    def test_frozen_config_rejects_changes(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT) as tmp:
            directory=Path(tmp)
            frozen_config(directory,{'model':'fixed'})
            frozen_config(directory,{'model':'fixed'})
            with self.assertRaises(ValueError):
                frozen_config(directory,{'model':'changed'})

    def test_row_materialization_is_atomic_and_preserves_unicode(self):
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT) as tmp:
            path=Path(tmp)/'records.jsonl'
            rows=[{'id':'a','question':'độc lập'}]
            save_rows(path,rows)
            self.assertEqual([json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()],rows)
            self.assertFalse(path.with_suffix('.tmp').exists())


if __name__=='__main__':
    unittest.main()
