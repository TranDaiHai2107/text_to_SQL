"""Review or delete expired Phase A scalar artifacts. Manual invocation required."""
from __future__ import annotations

import argparse
import json

from ehrqa.cli.bigquery_approved_smoke import RESULT_ROOT
from ehrqa.clinsql.phase_a_retention import expire_phase_a_artifacts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delete-expired', action='store_true')
    args = parser.parse_args(argv)
    outcomes = expire_phase_a_artifacts(RESULT_ROOT, delete_expired=args.delete_expired)
    print(json.dumps({'result_root': str(RESULT_ROOT), 'outcomes': outcomes,
                      'deletion_performed': args.delete_expired}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
