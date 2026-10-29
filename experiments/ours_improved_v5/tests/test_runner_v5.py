from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from infrastructure_v5 import load,V3
from run_v5 import plan_v5,selected_answer


class RunnerTests(unittest.TestCase):
    def test_new_audit_disjoint_from_every_previous_partition(self):
        plan=plan_v5()
        old=load(V3/'runs/deepseek_flash_v3_20261029_r2/protocol.json')['calibration_plan']
        v2=load(V3.parent/'ours_improved_v2/runs/deepseek_flash_v2b_20261028/threshold.json')['plan']
        previous=set(old['tune']+old['audit']+v2['tune']+v2['audit'])
        previous.update(load(V3.parent/'ours_improved_v4/runs/deepseek_flash_v4_20261029_r1/protocol.json')['plan']['audit'])
        self.assertEqual(plan['tune'],old['tune'])
        self.assertEqual(len(plan['audit']),100)
        self.assertFalse(set(plan['audit'])&previous)
        self.assertFalse(set(plan['audit'])&set(plan['tune']))

    def test_raw_reference_does_not_inherit_new_guard_null_result(self):
        row={'id':'q','candidates':[{'sql':'null'}]}
        raw={'sql':'SELECT 1','selected_candidate_index':0}
        with patch('run_v5.sql_answer',return_value=[(1,)]) as call:
            self.assertEqual(selected_answer(row,raw,{'q':['null']}),[(1,)])
            call.assert_called_once_with(raw)
        self.assertEqual(selected_answer(row,{'sql':'null','selected_candidate_index':None},{'q':['null']}),'null')


if __name__=='__main__':
    unittest.main()
