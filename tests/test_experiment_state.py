"""Offline experiment manifest and checkpoint gates; no benchmark test reads."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ehrqa.clinsql import experiment_state as state
from ehrqa.clinsql.experiment_state import ExperimentState


def test_pre_freeze_manifest_never_reads_test(monkeypatch):
    original = state.load_official_questions
    seen = []
    def checked(*args, **kwargs):
        seen.append(kwargs.get('split'))
        assert kwargs.get('split') == 'validation'
        return original(*args, **kwargs)
    monkeypatch.setattr(state, 'load_official_questions', checked)
    index = json.loads(Path('data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json').read_text())
    manifest = state.build_pre_freeze_manifest(
        Path('external/clinsql_official'),
        Path('data/clinsql/pilot_5_validation_development_v1.json'),
        schema_sha256='46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d',
        schema_index_sha256=index['sha256'], model_id='gpt-5-mini-2025-08-07')
    state.verify_pre_freeze_manifest(manifest)
    assert seen == ['validation']
    assert len(manifest['development_case_ids']) == 152
    assert len(manifest['internal_check_case_ids']) == 38
    assert manifest['test_scope'] == 'LOCKED_UNTIL_CONFIG_FREEZE'
    assert manifest['test_question_tree_sha256'] is None


def test_experiment_checkpoint_is_idempotent_and_seals_test(tmp_path):
    index = json.loads(Path('data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json').read_text())
    manifest = state.build_pre_freeze_manifest(
        Path('external/clinsql_official'),
        Path('data/clinsql/pilot_5_validation_development_v1.json'),
        schema_sha256='46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d',
        schema_index_sha256=index['sha256'], model_id='gpt-5-mini-2025-08-07')
    store = ExperimentState(tmp_path / 'state.sqlite', manifest)
    case_id = manifest['pilot_case_ids'][0]
    store.claim('PILOT_5', 'clinsql_cot', case_id)
    with pytest.raises(FileExistsError):
        store.claim('PILOT_5', 'clinsql_cot', case_id)
    store.finish('PILOT_5', 'clinsql_cot', case_id,
                 status='MODEL_SQL_ERROR', artifact_sha256='a' * 64)
    assert store.checkpoints('PILOT_5')[0].status == 'MODEL_SQL_ERROR'
    with pytest.raises(PermissionError):
        store.claim('TEST_443', 'clinsql_cot', case_id)
    modified = {**manifest, 'schema_sha256': 'b' * 64}
    modified['sha256'] = state._digest({k: v for k, v in modified.items() if k != 'sha256'})
    with pytest.raises(PermissionError, match='scope'):
        ExperimentState(tmp_path / 'state.sqlite', modified)
