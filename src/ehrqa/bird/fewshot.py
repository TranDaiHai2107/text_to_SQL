"""Few-shot layer: BM25 over BIRD *train* (question + evidence), fixed top 3.

Train and dev share no database or question (checked when the corpus is loaded), so a
demonstration can show SQL patterns but never the current question's answer.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from rank_bm25 import BM25Okapi

FEW_SHOT = 3


def _tokens(text: str) -> list[str]:
    return re.findall(r'[0-9a-z]+', text.casefold())


class TrainExamples:
    def __init__(self, train_file: Path, dev_questions: list[dict]):
        rows = json.loads(Path(train_file).read_text(encoding='utf-8'))
        dev_dbs = {r['db_id'] for r in dev_questions}
        dev_text = {r['question'].strip().casefold() for r in dev_questions}
        if any(r['db_id'] in dev_dbs or r['question'].strip().casefold() in dev_text for r in rows):
            raise ValueError('Few-shot corpus overlaps BIRD dev')
        self.rows = rows
        self.bm25 = BM25Okapi([_tokens(r['question'] + ' ' + r['evidence']) for r in rows])

    def __call__(self, question: str) -> dict:
        scores = self.bm25.get_scores(_tokens(question))
        best = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:FEW_SHOT]
        items = [{'question': self.rows[i]['question'], 'external_knowledge': self.rows[i]['evidence'],
                  'sql': self.rows[i]['SQL'], 'source': 'bird_train'} for i in best]
        return {'items': items, 'retrieval_kind': 'bm25_bird_train_question_evidence',
                'note': 'Different databases; demonstrations show SQL patterns only.'}
