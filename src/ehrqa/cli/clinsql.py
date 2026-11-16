"""Offline CLINSQL preflight. This command never calls BigQuery or an LLM."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ehrqa.clinsql.dataset import load_official_questions, load_questions, validation_partition


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--official-root', type=Path, help='Cloned official ClinSQL repository or data/splits')
    source.add_argument('--questions', type=Path, help='CLINSQL JSON/JSONL export')
    parser.add_argument('--seed', default='clinsql-2026-v1')
    parser.add_argument('--holdout-percent', type=int, default=20)
    args = parser.parse_args(argv)
    rows, digest = (load_official_questions(args.official_root) if args.official_root
                    else load_questions(args.questions))
    partitions = validation_partition(rows, seed=args.seed, holdout_percent=args.holdout_percent)
    print(json.dumps({'execution': False, 'dataset_sha256': digest, 'validation_questions': len(rows),
                      'development': len(partitions['development']),
                      'internal_check': len(partitions['internal_check']),
                      'partition': partitions}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
