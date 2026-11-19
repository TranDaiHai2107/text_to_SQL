"""Use the locked official ClinSQL prompt and SQL cleaning implementations.

The source checkout stays unmodified and is required for this baseline.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re


_SOURCE = Path(__file__).resolve().parents[3] / 'external' / 'clinsql_official' / 'utils'
_SOURCE_PROJECT = 'physionet-data'
_DATASETS = ('mimiciv_3_1_hosp', 'mimiciv_3_1_icu')


def _bind_bigquery_datasets(prompt: str, schema_text: str) -> str:
    """Replace only the source's dataset project, using the supplied DDL."""
    refs = re.findall(r'CREATE\s+TABLE\s+`([A-Za-z0-9_-]+)\.'
                      r'(mimiciv_3_1_(?:hosp|icu))\.[A-Za-z0-9_]+`',
                      schema_text, flags=re.I)
    if not refs:
        return prompt  # Synthetic unit schemas may omit fully qualified MIMIC DDL.
    projects = {project for project, _ in refs}
    roles = {dataset for _, dataset in refs}
    if len(projects) != 1 or roles != set(_DATASETS):
        raise ValueError('Schema DDL does not identify one complete BigQuery project')
    project = projects.pop()
    for dataset in _DATASETS:
        source_ref = f'{_SOURCE_PROJECT}.{dataset}'
        if source_ref not in prompt:
            raise ValueError('Locked CLINSQL prompt lacks its source dataset reference')
        prompt = prompt.replace(source_ref, f'{project}.{dataset}')
    return prompt


def _source_function(module_name: str, function_name: str):
    path = _SOURCE / f'{module_name}.py'
    if not path.is_file():
        raise FileNotFoundError(f'Locked official ClinSQL source missing: {path}')
    spec = importlib.util.spec_from_file_location(f'_clinsql_official_{module_name}', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load official ClinSQL source: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function_name)


def generation_prompt(question: str, schema_text: str) -> str:
    if not question or not schema_text:
        raise ValueError('Question and schema are required')
    source = _source_function('prompt_utils', 'build_generation_prompt')(question, schema_text)
    return _bind_bigquery_datasets(source, schema_text)


def refinement_prompt(question: str, schema_text: str, previous_sql: str, redacted_error: str) -> str:
    if not all((question, schema_text, previous_sql, redacted_error)):
        raise ValueError('Question, schema, previous SQL and redacted error are required')
    source = _source_function('prompt_utils', 'build_refinement_prompt')(
        question, previous_sql, redacted_error, schema_text
    )
    return _bind_bigquery_datasets(source, schema_text)


def extract_sql(text: str) -> str:
    return _source_function('sql_utils', 'clean_sql_response')(text)
