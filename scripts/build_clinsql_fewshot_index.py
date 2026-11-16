"""Build a pinned development-only few-shot corpus, offline."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ehrqa.clinsql.retrieval_manifest import build_development_fewshot_manifest


def main() -> None:
    master = json.loads((ROOT / 'data/clinsql/master_experiment_pre_freeze_v1.json').read_text(encoding='utf-8'))
    manifest = build_development_fewshot_manifest(ROOT / 'external/clinsql_official', master)
    target = ROOT / 'data/clinsql/retrieval/fewshot_development_v1.json'
    content = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_text(encoding='utf-8') != content:
            raise FileExistsError('Frozen few-shot corpus differs; do not overwrite')
    else:
        target.write_text(content, encoding='utf-8')
    print(json.dumps({'path': str(target), 'sha256': manifest['sha256'],
                      'examples': manifest['example_count']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
