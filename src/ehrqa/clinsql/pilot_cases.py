"""Frozen five-case selection from public validation question text only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .dataset import load_official_questions, validation_partition

SEED = 'clinsql-2026-v1'
RULE = 'development_only_sha256_order_2_easy_2_medium_1_hard_distinct_domains_v1'
COUNTS = {'easy_level_queries': 2, 'medium_level_queries': 2,
          'hard_level_queries': 1}


def select_pilot_cases(benchmark_root: Path) -> dict:
    questions, source_hash = load_official_questions(benchmark_root, split='validation')
    partitions = validation_partition(questions, seed=SEED)
    if (len(questions), len(partitions['development']), len(partitions['internal_check'])) != (190, 152, 38):
        raise ValueError('Validation partition differs from pinned 152/38 split')
    development = set(partitions['development'])
    chosen, domains = [], set()
    for difficulty, count in COUNTS.items():
        pool = sorted((q for q in questions if q.query_id in development and q.difficulty == difficulty),
                      key=lambda q: (hashlib.sha256(f'{SEED}:{q.query_id}'.encode()).hexdigest(), q.query_id))
        for question in pool:
            if question.domain in domains:
                continue
            chosen.append(question)
            domains.add(question.domain)
            if sum(q.difficulty == difficulty for q in chosen) == count:
                break
    if len(chosen) != 5 or len(domains) != 5:
        raise ValueError('Cannot select five distinct-domain validation development cases')
    cases = [{'case_id': q.query_id, 'split': q.split, 'domain': q.domain,
              'difficulty': q.difficulty,
              'question_sha256': hashlib.sha256(q.text.encode('utf-8')).hexdigest()}
             for q in chosen]
    payload = {'version': 1, 'seed': SEED, 'rule': RULE,
               'source_question_tree_sha256': source_hash,
               'development_count': 152, 'internal_check_count': 38, 'cases': cases}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {**payload, 'sha256': digest}


def verify_pilot_cases(path: Path, benchmark_root: Path) -> dict:
    actual = json.loads(Path(path).read_text(encoding='utf-8'))
    if actual != select_pilot_cases(benchmark_root):
        raise ValueError('Pilot case manifest differs from public validation inputs or locked selection rule')
    return actual
