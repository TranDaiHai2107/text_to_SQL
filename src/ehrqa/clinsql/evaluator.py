"""CLINSQL official scorer boundary. Never substitute a local metric for paper scores."""
from __future__ import annotations

from pathlib import Path


class OfficialClinSQLEvaluator:
    def __init__(self, source_root: Path, *, source_commit: str, judge_config_hash: str):
        self.source_root = Path(source_root)
        self.source_commit = source_commit
        self.judge_config_hash = judge_config_hash

    def evaluate_saved_predictions(self, prediction_dir: str, *, split: str) -> dict:
        if split not in {'validation', 'test'}:
            raise ValueError('Unknown split')
        if not self.source_commit or not self.judge_config_hash:
            raise ValueError('Official scorer and judge configuration must be pinned')
        if not (self.source_root / 'evaluation' / 'clinical_rubric_scorer.py').is_file():
            raise FileNotFoundError('Official CLINSQL scorer is not installed')
        if not Path(prediction_dir).is_dir():
            raise FileNotFoundError(prediction_dir)
        raise RuntimeError('Scorer invocation and output mapping require verification against the pinned official repository; no score was produced')
