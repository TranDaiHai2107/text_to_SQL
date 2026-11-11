"""Load public CLINSQL question inputs without exposing reference fields to inference."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True)
class Question:
    query_id: str
    split: str
    domain: str
    difficulty: str
    text: str


def _rows(path: Path):
    if path.suffix == '.jsonl':
        yield from (json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip())
    elif path.suffix == '.json':
        payload = json.loads(path.read_text(encoding='utf-8'))
        yield from payload['data'] if isinstance(payload, dict) and 'data' in payload else payload
    else:
        raise ValueError('Expected JSON or JSONL CLINSQL export')


def load_questions(path: Path, *, allow_test: bool = False) -> tuple[list[Question], str]:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    questions = []
    seen = set()
    for row in _rows(path):
        split = str(row['split']).lower()
        if split == 'test' and not allow_test:
            raise PermissionError('Test split is locked until the experiment configuration is frozen')
        if split not in {'validation', 'test'}:
            raise ValueError(f'Unexpected CLINSQL split: {split}')
        qid = f"{row['domain']}/{row['difficulty']}/{row['problem_id']}"
        key = (split, qid)
        if key in seen:
            raise ValueError(f'Duplicate question ID: {key}')
        seen.add(key)
        questions.append(Question(qid, split, str(row['domain']), str(row['difficulty']), str(row['query'])))
    return questions, digest


def validation_partition(questions: list[Question], *, seed: str, holdout_percent: int = 20):
    if not 0 < holdout_percent < 100:
        raise ValueError('Holdout percentage must be between 0 and 100')
    if any(q.split != 'validation' for q in questions):
        raise ValueError('Partition only the validation split')
    groups = {'development': [], 'internal_check': []}
    for q in questions:
        bucket = int(hashlib.sha256((seed + ':' + q.query_id).encode()).hexdigest(), 16) % 100
        groups['internal_check' if bucket < holdout_percent else 'development'].append(q.query_id)
    return groups
