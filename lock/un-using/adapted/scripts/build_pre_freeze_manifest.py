"""Rebuild and verify the validation-only master experiment manifest offline."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ehrqa.clinsql.experiment_state import build_pre_freeze_manifest
from ehrqa.clinsql.metadata import verify_schema_manifest
from ehrqa.clinsql.schema_index import SchemaIndex


def main() -> None:
    schema = json.loads((ROOT / 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json')
                        .read_text(encoding='utf-8'))
    verify_schema_manifest(schema)
    index = SchemaIndex.load(
        ROOT / 'data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json', schema)
    manifest = build_pre_freeze_manifest(
        ROOT / 'external/clinsql_official',
        ROOT / 'data/clinsql/pilot_5_validation_development_v1.json',
        schema_sha256=schema['sha256'],
        schema_index_sha256=index.index['sha256'],
        model_id='gpt-5-mini-2025-08-07')
    path = ROOT / 'data/clinsql/master_experiment_pre_freeze_v2.json'
    content = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') != content:
        raise ValueError('Existing experiment manifest differs from locked inputs')
    if not path.exists():
        path.write_text(content, encoding='utf-8')
    print(json.dumps({'path': str(path), 'sha256': manifest['sha256'],
                      'development_count': 152, 'internal_check_count': 38,
                      'pilot_count': 5,
                      'test_scope': manifest['test_scope']}))


if __name__ == '__main__':
    main()
