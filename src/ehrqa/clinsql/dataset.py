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


def load_official_questions(
    repository: Path, *, split: str = 'validation', allow_test: bool = False,
    expected_count: int | None = None,
) -> tuple[list[Question], str]:
    """Read only query text from the official ClinSQL directory tree.

    Reference SQL, result CSVs and rubric JSONs are deliberately never opened.
    The returned digest covers relative paths and exact query bytes in sorted
    order, so a changed benchmark question changes the preflight fingerprint.
    """
    if split not in {'validation', 'test'}:
        raise ValueError(f'Unexpected CLINSQL split: {split}')
    if split == 'test' and not allow_test:
        raise PermissionError('Test split is locked until the experiment configuration is frozen')
    repository = Path(repository)
    splits = repository / 'data' / 'splits'
    if not splits.is_dir():
        splits = repository / 'splits'
    if not splits.is_dir():
        splits = repository
    split_dir = splits / split
    if not split_dir.is_dir():
        raise FileNotFoundError(f'Official CLINSQL split not found: {split_dir}')

    files = sorted(split_dir.glob('*/*/*/query_*.txt'))
    if not files:
        raise ValueError(f'No CLINSQL questions found in {split_dir}')
    expected_count = expected_count if expected_count is not None else {'validation': 190, 'test': 443}[split]
    if len(files) != expected_count:
        raise ValueError(f'Incomplete CLINSQL {split} split: expected {expected_count}, found {len(files)}')
    digest = hashlib.sha256()
    questions: list[Question] = []
    seen: set[str] = set()
    for path in files:
        problem_id = path.parent.name
        if path.name != f'query_{problem_id}.txt':
            raise ValueError(f'Question filename and ID disagree: {path}')
        domain, difficulty = path.parts[-4:-2]
        query_id = f'{domain}/{difficulty}/{problem_id}'
        if query_id in seen:
            raise ValueError(f'Duplicate question ID: {query_id}')
        seen.add(query_id)
        raw = path.read_bytes()
        question = raw.decode('utf-8').strip()
        if not question:
            raise ValueError(f'Empty CLINSQL question: {path}')
        relative = path.relative_to(split_dir).as_posix().encode('utf-8')
        digest.update(len(relative).to_bytes(4, 'big'))
        digest.update(relative)
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
        questions.append(Question(query_id, split, domain, difficulty, question))
    return questions, digest.hexdigest()


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
