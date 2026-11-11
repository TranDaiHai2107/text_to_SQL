"""Render the real UI offline: no inference, database connection or fallback API."""
from pathlib import Path
import tempfile

import pandas as pd
import pytest

from ehrqa import rag_engine
from ehrqa.agentic.gateway import Gateway


@pytest.mark.parametrize('status',['answered','abstained','error'])
def test_full_agentic_ui_displays_all_decisions_without_extra_calls(monkeypatch,status,tmp_path):
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path))
    # AppTest allocates a module-level TemporaryDirectory on import. Keep that
    # directory in the writable workspace too, including its exit-time cleanup.
    from streamlit.testing.v1 import AppTest
    calls=[]
    def run(question,**kwargs):
        calls.append(question)
        return {'status':status,'success':status=='answered','sql':'SELECT COUNT(*) FROM admissions' if status=='answered' else 'null' if status=='abstained' else '',
                'reason':'Diagnostic decision','ctx':{},'attempts':1,'history':[{'attempt':1,'sql':'SELECT 1','error':None}],
                'df':pd.DataFrame({'count':[42]}) if status=='answered' else None,'answer':'There are 42 admissions.',
                'model_calls':8,'trace':[]}
    def unexpected(*args,**kwargs):pytest.fail('UI rendering must not issue another API call')
    monkeypatch.setattr(rag_engine,'generate_sql_with_correction',run)
    monkeypatch.setattr(rag_engine,'call_llm',unexpected)
    monkeypatch.setattr(Gateway,'complete',unexpected)
    app=AppTest.from_file(str(Path(rag_engine.__file__).with_name('app.py'))).run(timeout=20)
    assert not app.exception
    app.chat_input[0].set_value('How many admissions?').run(timeout=20)
    assert not app.exception and calls==['How many admissions?']
    display=app.session_state['messages'][-1]['display']
    if status=='answered':assert display=='There are 42 admissions.'
    elif status=='abstained':assert 'Chưa đủ bằng chứng' in display and not app.error
    else:assert 'Diagnostic decision' in display
