"""Check the pinned inference model without printing credentials or prompts."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path

from ehrqa.clinsql.openai_provider import OpenAIModelProvider
from ehrqa.clinsql.pilot_api_budget import PilotAPIBudget, PersistentAPIBudgetLedger


ROOT = Path(__file__).resolve().parents[3]
MODEL = 'gpt-5-mini-2025-08-07'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--generate', action='store_true',
                      help='Send one paid, nonclinical Responses request')
    mode.add_argument('--diagnose', action='store_true',
                      help='Send one bounded synthetic long-prompt transport request')
    args = parser.parse_args(argv)
    if not os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY is unavailable in process')
    if os.environ.get('OPENAI_MODEL') != MODEL:
        raise PermissionError('Model differs from pinned research snapshot')
    from openai import OpenAI
    client = OpenAI(max_retries=0, timeout=30)
    try:
        found = client.models.retrieve(MODEL)
    except Exception as exc:
        print(json.dumps({'model_access': 'FAIL', 'error_type': type(exc).__name__,
                          'http_status': getattr(exc, 'status_code', None)}))
        return 2
    if found.id != MODEL:
        raise RuntimeError('Retrieved model ID differs from pinned snapshot')
    output = {'model_access': 'PASS', 'model_id': found.id}
    if args.generate or args.diagnose:
        output_cap = 8192 if args.diagnose else 512
        prompt = ('Return the single word OK. Synthetic identifiers: ' +
                  ('table_alpha column_beta ' * 450)) if args.diagnose else 'Reply with the single word OK.'
        budget = PilotAPIBudget(1, 20000 if args.diagnose else 1000,
                                output_cap, None, Decimal('0.25'),
                                Decimal('2.00'), 'UNLIMITED_RESEARCH_NOV_2026')
        ledger = PersistentAPIBudgetLedger(
            ROOT / 'results/restricted/phase_c1_state' /
            ('openai_transport_diagnostic_v1.sqlite' if args.diagnose else
             'openai_access.sqlite'), budget)
        provider = OpenAIModelProvider(
            ledger, model_id=MODEL, max_output_tokens=output_cap,
            timeout_seconds=90 if args.diagnose else 30,
            reasoning_effort=os.environ.get('OPENAI_REASONING_EFFORT'),
            client=client)
        try:
            response = provider.complete('transport_diagnostic' if args.diagnose
                                         else 'access_probe', prompt)
        except Exception as exc:
            output.update({'responses_access': 'FAIL',
                           'error_type': type(exc).__name__,
                           'cause_type': getattr(exc, 'cause_type', None),
                           'http_status': getattr(exc, 'http_status', None),
                           'ledger': ledger.snapshot()})
            print(json.dumps(output))
            return 3
        output.update({'responses_access': 'PASS',
                       'returned_model': response['model_snapshot'],
                       'response_id': response['response_id'],
                       'usage': response['usage'],
                       'ledger': ledger.snapshot()})
    print(json.dumps(output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
