"""Reproducibility utilities, separate from legacy modules named common."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
EXPERIMENTS = ROOT.parent
BASELINE = WORKSPACE / 'baselines/probgate_ehrsql_2024'
V3 = EXPERIMENTS / 'ours_improved_v3'
V4 = EXPERIMENTS / 'ours_improved_v4'
V5 = EXPERIMENTS / 'ours_improved_v5'
VANNA = EXPERIMENTS / 'vanna_ehrsql'
V3_RUN = V3 / 'runs/deepseek_flash_v3_20261029_r2'
V4_RUN = V4 / 'runs/deepseek_flash_v4_20261029_r1'
V5_RUN = V5 / 'runs/deepseek_flash_v5_20261029_r1'
DB = BASELINE / 'upstream/src/data/mimic_iv/mimic_iv.sqlite'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def object_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def freeze(path, value):
    if Path(path).exists():
        if load(path) != value:
            raise ValueError(f'Immutable artifact changed: {path}')
    else:
        dump(path, value)


def normalized(text):
    return re.sub(r'\W+', ' ', text.casefold()).strip()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def known_inputs():
    """Input questions only, including every split already used in this project."""
    rows = []
    for split in ('train', 'dev', 'test'):
        rows += [{**r, 'split': split} for r in load(BASELINE / f'data/inputs/{split}.json')['data']]
    return rows


def activate_methods():
    for folder in (V5, V4, V3, BASELINE):
        if str(folder) not in sys.path:
            sys.path.insert(1, str(folder))


def checked_name(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
        raise ValueError('Use a simple alphanumeric dataset/run name')
    return name


def verify_files(manifest):
    changed = [name for name, digest in manifest.items()
               if not (WORKSPACE / name).is_file() or sha(WORKSPACE / name) != digest]
    if changed:
        raise ValueError('Frozen files changed: ' + ', '.join(changed[:8]))


def verify_lock():
    lock = load(ROOT / 'V5_LOCK.json')
    verify_files(lock['files'])
    return lock


def verify_protocol():
    lock = load(ROOT / 'PROTOCOL_LOCK.json')
    if sha(ROOT / 'protocol.json') != lock['protocol_sha256']:
        raise ValueError('Protocol changed after registration')
    verify_files(lock['implementation_sha256'])
    verify_lock()
    return load(ROOT / 'protocol.json')
