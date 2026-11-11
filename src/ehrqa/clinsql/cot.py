"""Offline CoT baseline specification from CLINSQL paper Appendix D.

Inference transport is deliberately not wired until model, BigQuery and data policy are locked.
"""
from __future__ import annotations

import re


DATASETS = ('physionet-data.mimiciv_3_1_hosp', 'physionet-data.mimiciv_3_1_icu')


def generation_prompt(question: str, schema_text: str, *, datasets=DATASETS) -> str:
    if not question or not schema_text:
        raise ValueError('Question and schema are required')
    return (
        'You are a clinical data analyst expert specializing in the MIMIC-IV database. '
        'Your goal is to produce a correct BigQuery SQL query for the question below.\n'
        'Constraints:\n- Target platform: Google BigQuery.\n- Use the correct datasets:\n'
        + ', '.join(datasets) + '.\nMIMIC-IV Schema Reference (HOSP + ICU):\n'
        + schema_text + '\nClinical question:\n“' + question + '”\n' +
        'Your output should be organized in the following two parts:\n'
        'Reasoning:\n- Think step by step about relevant tables, joins, filters, groupings, and edge cases.\n'
        '- Briefly justify important choices.\n'
        'SQL (wrap the final query in a fenced code block using ```sql and ```):\n'
        'Think step by step and then generate the complete SQL query.'
    )


def refinement_prompt(question: str, schema_text: str, previous_sql: str, redacted_error: str,
                      *, datasets=DATASETS) -> str:
    if not all((question, schema_text, previous_sql, redacted_error)):
        raise ValueError('Question, schema, previous SQL and redacted error are required')
    return (
        'You are a clinical data analyst expert for the MIMIC-IV dataset. '
        'The following SQL failed to run on Google BigQuery. Refine it to resolve the error and better answer the question.\n'
        'Constraints:\n- Use valid BigQuery SQL.\n- Use the correct datasets:\n'
        + ', '.join(datasets) + '.\nMIMIC-IV Schema Reference (HOSP + ICU):\n'
        + schema_text + '\nClinical question:\n“' + question + '”\nPrevious SQL:\n```sql\n' +
        previous_sql + '\n```\nBigQuery error message:\n' + redacted_error + '\n' +
        'Your output should be organized in the following two parts:\nReasoning:\n'
        '- Step by step, explain the cause of the error and the fix.\n'
        '- Justify key changes briefly.\nSQL (wrap the final corrected query in a fenced code block using ```sql and ```):\n'
        'Think step by step and then generate the complete corrected SQL query.'
    )


def extract_sql(text: str) -> str:
    blocks = re.findall(r'```(?:sql)?\s*(.*?)```', text, flags=re.IGNORECASE | re.DOTALL)
    if len(blocks) != 1 or not blocks[0].strip():
        raise ValueError('Expected exactly one fenced SQL block')
    return blocks[0].strip()
