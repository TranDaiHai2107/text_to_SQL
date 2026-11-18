"""The CLINSQL CoT and SDE-SQL baselines are frozen after validation v9.

Their reproduction was reviewed against the official sources (PAPER_SOURCE_LOCK.json) and
the documented deviations in BASELINE_LOCK.json. Any edit to a locked file fails this test:
baselines must not be tuned further, so every later Ours result is compared against the
same baseline code. Hashes use LF-normalised bytes so a git line-ending conversion is not
mistaken for an edit.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'BASELINE_LOCK.json').read_text(encoding='utf-8'))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def test_locked_baseline_files_are_unchanged():
    changed = [name for name, expected in LOCK['files'].items() if _digest(ROOT / name) != expected]
    assert not changed, f'Locked baseline files changed (baselines are frozen): {changed}'


def test_lock_covers_both_baselines_and_their_shared_adapters():
    files = set(LOCK['files'])
    assert {'src/ehrqa/clinsql/cot.py', 'src/ehrqa/clinsql/cot_runner.py'} <= files
    assert {'src/ehrqa/clinsql/baselines/sde_sql.py', 'src/ehrqa/clinsql/baselines/sde_judge.py',
            'src/ehrqa/clinsql/baselines/sde_refine_policy.py',
            'src/ehrqa/clinsql/baselines/sde_subqueries.py'} <= files
    assert 'src/ehrqa/clinsql/execution_errors.py' in files
    assert LOCK['status'] == 'LOCKED'
    assert LOCK['settings']['model'] == 'gpt-5-mini-2025-08-07'
    assert LOCK['settings']['reasoning_effort'] == 'medium'


def test_official_sources_stay_pinned():
    sources = json.loads((ROOT / 'PAPER_SOURCE_LOCK.json').read_text(encoding='utf-8'))
    for method in ('clinsql', 'sde_sql'):
        for name, expected in sources[method]['key_files'].items():
            path = ROOT / sources[method]['path'] / name
            raw = hashlib.sha256(path.read_bytes()).hexdigest()
            assert expected in (raw, _digest(path)), f'{method}: {name} differs from the pinned checkout'
