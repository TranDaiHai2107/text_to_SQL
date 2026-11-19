"""Verify exact, unmodified official source snapshots without running models or databases."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'lock' / 'un-using' / 'PAPER_SOURCE_LOCK.json'


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def verify_sources() -> dict:
    locked = json.loads(LOCK.read_text(encoding='utf-8'))
    result = {}
    for name, spec in locked.items():
        repo = ROOT / spec['path']
        if not repo.is_dir():
            raise FileNotFoundError(f'{name}: {repo}')
        commit = git(repo, 'rev-parse', 'HEAD')
        tree = git(repo, 'rev-parse', 'HEAD^{tree}')
        if (commit, tree) != (spec['commit'], spec['tree']):
            raise ValueError(f'{name}: source commit/tree differs from lock')
        changes = git(repo, 'status', '--porcelain', '--untracked-files=no')
        if changes:
            raise ValueError(f'{name}: official tracked files were modified')
        for relative, expected in spec['key_files'].items():
            digest = hashlib.sha256((repo / relative).read_bytes()).hexdigest()
            if digest != expected:
                raise ValueError(f'{name}: modified key file {relative}')
        result[name] = {'path': str(repo), 'commit': commit, 'verified_key_files': len(spec['key_files'])}
    split = ROOT / locked['clinsql']['path'] / 'data' / 'splits'
    for label, expected in [('validation', 190), ('test', 443)]:
        count = sum(1 for _ in (split / label).rglob('query_*.txt'))
        if count != expected:
            raise ValueError(f'CLINSQL {label}: expected {expected} questions, found {count}')
        result['clinsql'][f'{label}_questions'] = count
    return result


if __name__ == '__main__':
    print(json.dumps(verify_sources(), ensure_ascii=False, indent=2))
