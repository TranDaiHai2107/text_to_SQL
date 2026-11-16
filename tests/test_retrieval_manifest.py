"""Frozen few-shot examples never contain pilot, holdout or test gold."""
import hashlib
import json
from pathlib import Path

import pytest

from ehrqa.clinsql.retrieval_manifest import (
    FROZEN_CORPUS_SHA256, build_development_fewshot_manifest, load_frozen_fewshot_index,
    verify_development_fewshot_manifest)


ROOT = Path(__file__).resolve().parents[1]
MASTER = json.loads((ROOT / 'data/clinsql/master_experiment_pre_freeze_v1.json').read_text(encoding='utf-8'))
SOURCE = ROOT / 'external/clinsql_official'
FROZEN = ROOT / 'data/clinsql/retrieval/fewshot_development_v1.json'


def test_frozen_corpus_matches_source_and_excludes_other_splits():
    actual = json.loads(FROZEN.read_text(encoding='utf-8'))
    assert actual['sha256'] == FROZEN_CORPUS_SHA256
    verify_development_fewshot_manifest(actual, MASTER)
    assert actual == build_development_fewshot_manifest(SOURCE, MASTER)
    ids = {row['query_id'] for row in actual['examples']}
    assert len(ids) == 145
    assert not ids & set(MASTER['pilot_case_ids'])
    assert not ids & set(MASTER['internal_check_case_ids'])
    assert all('physionet-data.' not in row['sql'] for row in actual['examples'])
    index = load_frozen_fewshot_index(FROZEN, MASTER)
    question = actual['examples'][0]
    retrieved = index.retrieve(question['question'], query_id=question['query_id'])
    assert all(row['source_id'] != question['query_id'] for row in retrieved['items'])


def test_loader_rejects_self_consistent_but_unpinned_corpus(tmp_path):
    actual = json.loads(FROZEN.read_text(encoding='utf-8'))
    actual['examples'][0]['question'] += ' synthetic change'
    payload = {key: value for key, value in actual.items() if key != 'sha256'}
    actual['sha256'] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    verify_development_fewshot_manifest(actual, MASTER)
    path = tmp_path / 'corpus.json'
    path.write_text(json.dumps(actual), encoding='utf-8')
    with pytest.raises(ValueError, match='pinned experiment version'):
        load_frozen_fewshot_index(path, MASTER)
