"""Grade the completed OpenAI run offline by explicit paths, avoiding Vanna's score.py name collision."""
import importlib.util
import json
from pathlib import Path
import sys
import time

WORKSPACE=Path(__file__).resolve().parents[2]
ROOT=WORKSPACE/'experiments/openai_economy_standard_finish'
RUN=ROOT/'runs/gpt6luna_none_complete_20261030_once'


def main():
    sys.path.insert(0,str(ROOT))
    # The scorer imports 'run'. Pin it before legacy modules reorder sys.path.
    spec=importlib.util.spec_from_file_location('run',ROOT/'run.py')
    runner=importlib.util.module_from_spec(spec)
    sys.modules['run']=runner
    spec.loader.exec_module(runner)
    scorer_spec=importlib.util.spec_from_file_location('_openai_economy_offline_score',ROOT/'score.py')
    scorer=importlib.util.module_from_spec(scorer_spec)
    scorer_spec.loader.exec_module(scorer)
    report=scorer.score_run(RUN)
    from validation_common import dump
    state={'state':'complete','run':RUN.name,'model':report['model'],'reasoning_effort':'none',
           'completed_questions':1167,'expected_questions':1167,
           'new_API_calls_for_scoring':0,'scoring_import_collision_resolved_by_explicit_module_paths':True,
           'updated_at_unix':time.time()}
    dump(RUN/'status.json',state)
    dump(ROOT/'STATUS.json',state)
    print(json.dumps({'state':'complete','new_API_calls':0,'variants':{
        name:{'scores':m['scores'],'EX':m['EX'],'VSR':m['VSR'],'wrong':m['wrong']}
        for name,m in report['variants'].items()}},indent=2))
    return report


if __name__=='__main__':
    main()
