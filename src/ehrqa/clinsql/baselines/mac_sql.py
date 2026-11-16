"""MAC-SQL Selector → Decomposer → Refiner against injected interfaces.

The original BIRD/Spider prompts are adapted for BigQuery. Execution and
column-value evidence are injected; no hidden SQLite or API calls occur.
"""
from __future__ import annotations

import json
import re
from sqlglot import exp, parse_one

from ehrqa.agentic.schema import Schema
from ..execution_errors import IncompleteResultError, SecurityRejected
from ..offline import MockBigQuery, MockLLM
from ..source_templates import constant
from .mac_sampling import native_selector_method, qualified_table, sample_column_values


def _sql(text: str) -> str:
    blocks = re.findall(r'```sql(.*?)```', text, re.S)
    return blocks[-1].strip() if blocks else 'error: No SQL found in the input string'


def _selector_response(text: str) -> dict:
    """Apply native first-fence and whole-response validation without printing evidence."""
    start = text.find('```json')
    end = text.find('```', start + 7)
    if start == -1 or end == -1:
        return {}
    try:
        selected = json.loads(text[start + 7:end])
    except ValueError:
        return {}
    if not isinstance(selected, dict) or not all(
        isinstance(choice, list) or choice in ('keep_all', 'drop_all')
        for choice in selected.values()
    ):
        return {}
    return selected


def _native_pruning_needed(schema: Schema) -> bool:
    """Mirror source Selector._is_need_prune (avg<=6 AND total<=30 means skip)."""
    total = sum(len(columns) for columns in schema.tables.values())
    average = total / len(schema.tables) if schema.tables else 0
    return not (average <= 6 and total <= 30)


def _fk_text(schema: Schema) -> str:
    edges = sorted(schema.edges, key=lambda edge: list(schema.tables).index(edge['left'].split('.')[0]))
    return '\n'.join(dict.fromkeys(
        f"{left_table}.`{left_column}` = {right_table}.`{right_column}`"
        for edge in edges
        for left_table, left_column in [edge['left'].split('.')]
        for right_table, right_column in [edge['right'].split('.')]
    ))


def _bigquery_schema_context(schema):
    names = []
    for table, ddl in schema.ddl.items():
        try:
            names.append(f'{table}: {qualified_table(ddl)}')
        except ValueError:
            continue  # Unqualified synthetic fixtures.
    if not names:
        return ''
    return ('\n\nGoogleSQL table names (use the full identifiers in SQL and short names '
            'in Selector JSON):\n' + '\n'.join(names))


def _key_columns(schema, records=()):
    keys = {table: set() for table in schema.tables}
    for record in records:
        table = record['table']
        keys[table].update(column for column in record.get('primary_keys', ())
                           if column in schema.tables[table])
    for edge in schema.edges:
        for endpoint in (edge['left'], edge['right']):
            table, column = endpoint.split('.')
            keys[table].add(column)
    return keys


def _chosen_columns(schema, selected, keys):
    chosen = {}
    for table, types in schema.tables.items():
        columns = list(types)
        choice = selected.get(table, 'keep_all')
        if choice == 'keep_all' or choice == '':
            chosen[table] = columns
        elif choice == 'drop_all':
            chosen[table] = columns[:6]
        else:
            first = [column for column in columns if column in keys[table] or column in choice]
            if len(columns) > 6:
                first += [column for column in columns if column not in first][:max(0, 6 - len(first))]
            chosen[table] = first
    return chosen


def _selected_schema_text(schema: Schema, selected: dict) -> str:
    """Native selector keeps unmentioned tables; selected columns retain join keys."""
    rendered = []
    for table, ordered in _chosen_columns(schema, selected, _key_columns(schema)).items():
        ddl = schema.ddl[table]
        if ordered == list(schema.tables[table]):
            rendered.append(ddl)
            continue
        by_name = {column.name: '  ' + column.sql(dialect='bigquery')
                   for column in parse_one(ddl, read='bigquery').find_all(exp.ColumnDef)}
        kept = [by_name[column] for column in ordered]
        rendered.append(ddl[:ddl.index('(') + 1] + '\n' + ',\n'.join(kept) + '\n)')
    return '\n'.join(rendered)


def _bird_schema_text(schema: Schema, selected: dict,
                      column_values: dict | None = None, *, records=()) -> str:
    """Port native BIRD list layout; BigQuery metadata supplies column names.

    Real column value examples require a separately approved provider. When
    absent they stay empty rather than fabricating values from patient data.
    """
    column_values = column_values or {}
    metadata = {record['table']: record.get('column_descriptions', {}) for record in records}
    parts = []
    for table, columns in _chosen_columns(schema, selected, _key_columns(schema, records)).items():
        lines = []
        for column in columns:
            description = metadata.get(table, {}).get(column, {})
            full_name = description.get('full_name', column)
            extra = description.get('description', '')
            values = column_values.get(table, {}).get(column, '')
            line = f'  ({column},'
            if full_name != '':
                line += f' {full_name.strip()}.'
            if values:
                line += f' Value examples: {values}.'
            if extra != '' and str(extra) != 'nan':
                line += ' ' + ('And ' + str(extra))[:100]
            lines.append(line + '),')
        parts.append(f"# Table: {table}\n[\n" + '\n'.join(lines).strip(',') + '\n]')
    return '\n'.join(parts)


def verify_bird_description(schema, samples, records):
    """Compare the port's actual description to the native BIRD renderer locally."""
    render = native_selector_method('_build_bird_table_schema_list_str')
    descriptions = {record['table']: record.get('column_descriptions', {}) for record in records}
    expected = []
    for table, columns in schema.tables.items():
        metadata = descriptions.get(table, {})
        labels = [(col, metadata.get(col, {}).get('full_name', col),
                   metadata.get(col, {}).get('description', '')) for col in columns]
        values = [(col, samples[table].get(col, '')) for col in columns]
        expected.append(render(None, table, labels, values))
    if ''.join(expected).strip() != _bird_schema_text(schema, {}, samples, records=records):
        raise ValueError('MAC database description differs from native renderer on the same evidence')


class MACSQL:
    def __init__(self, model, database, *, value_evidence, max_refinements=3,
                 sample_synthetic_values=False, sample_approved_values=False, approved_sampler=None):
        if value_evidence is None:
            raise ValueError('Selector value-evidence provider is required; do not silently omit it')
        if max_refinements != 3:
            raise ValueError('Native MAX_ROUND=3 permits three Refiner turns')
        self.model, self.db, self.value_evidence = model, database, value_evidence
        if sample_synthetic_values and not (
            isinstance(model, MockLLM) and isinstance(database, MockBigQuery)
        ):
            raise PermissionError('MAC-SQL value sampling in prompts requires both synthetic transports')
        self.sample_synthetic_values = sample_synthetic_values
        self.sample_approved_values = sample_approved_values
        self.approved_sampler = approved_sampler

    def run(self, question: str) -> dict:
        records = list(self.db.schema_metadata())
        schema = Schema.from_records(records, dialect='bigquery')
        values = self.value_evidence(question, schema)
        column_values = {}
        if isinstance(values, dict):
            column_values = values.get('column_values', {})
            values = values.get('evidence', '')
        if not isinstance(values, str):
            raise ValueError('Selector evidence must be an approved text summary')
        if not isinstance(column_values, dict):
            raise ValueError('Column value evidence must be a table/column mapping')
        if any(not isinstance(table_values, dict) for table_values in column_values.values()):
            raise ValueError('Column value evidence must be grouped by table')
        if any(value for table_values in column_values.values()
               for value in table_values.values()):
            raise PermissionError('Column value examples require a separate approved data policy')
        if values and not (
            isinstance(getattr(self.model, 'model', self.model), MockLLM)
            and isinstance(getattr(self.db, 'database', self.db), MockBigQuery)
        ):
            raise PermissionError('Free-text MAC-SQL evidence requires a separate approved data policy')
        keys = _key_columns(schema, records)
        if self.sample_synthetic_values or self.sample_approved_values:
            sampler = self.approved_sampler or sample_column_values
            column_values = sampler(self.db, schema, keys)
        catalog_context = _bigquery_schema_context(schema)
        desc = _bird_schema_text(schema, {}, column_values, records=records) + catalog_context
        selector = constant('mac_sql_official', 'core/const.py', 'selector_template')
        fk_text = _fk_text(schema)
        selected = {}
        if _native_pruning_needed(schema):
            prompt = selector.format(db_id='mimic_iv_3_1', query=question, evidence=values,
                                     desc_str=desc, fk_str=fk_text)
            reply = self.model.generate('mac.selector', prompt)[0]
            selected = _selector_response(reply['content'])
        selected_desc = _bird_schema_text(schema, selected, column_values, records=records) + catalog_context
        decomposer = constant('mac_sql_official', 'core/const.py', 'decompose_template_bird')
        prompt = decomposer.format(query=question, evidence=values,
                                   desc_str=selected_desc, fk_str=fk_text)
        reply = self.model.generate('mac.decomposer', prompt)[0]
        qa_pairs = reply['content'].strip()
        sql = _sql(qa_pairs)
        message = {'db_id': 'mimic_iv_3_1', 'query': question, 'evidence': values,
                   'desc_str': selected_desc, 'fk_str': fk_text,
                   'final_sql': sql, 'qa_pairs': qa_pairs, 'fixed': False,
                   'send_to': 'Refiner', 'try_times': 0,
                   'pruned': _native_pruning_needed(schema), 'extracted_schema': selected,
                   'chosen_db_schem_dict': _chosen_columns(schema, selected, keys)}
        attempts = []
        result = None
        status = 'generation_failure'
        for _ in range(3):
            status, result = self._refiner_turn(message, question, values, selected_desc, fk_text, attempts)
            if message['send_to'] == 'System':
                break
        if status == 'corrected_unexecuted' and message['pred'].startswith('error:'):
            status = 'generation_failure'
        return {'sql': message['pred'], 'status': status, 'attempts': attempts,
                'result': result, 'selector': selected, 'message': message}

    def _refiner_turn(self, message, question, evidence, desc, fk_text, attempts):
        sql = message.get('pred', message['final_sql'])
        message.update(pred=sql, send_to='System', try_times=message.get('try_times', 0) + 1)
        if 'error' in sql:
            return 'generation_failure', None
        try:
            self.db.dry_run(sql)
            result = self.db.execute(sql)
            if not result.complete:
                raise IncompleteResultError('Incomplete BigQuery result; benchmark execution cannot be scored')
            observed = result.rows[:5]  # native _execute_sql returns result[:5]
            error = ('no data selected' if not observed else
                     'exist None value, you can add `NOT NULL` in SQL'
                     if any(v is None for row in observed for v in row) else None)
            exception_class = ''
        except (ValueError, SecurityRejected) as exc:
            error = ('SQL rejected by the read-only guard' if isinstance(exc, SecurityRejected)
                     else 'BigQuery rejected the SQL; details withheld')
            exception_class = type(exc).__name__
            result = None
        attempts.append({'stage': 'refiner', 'sql': sql, 'error': error,
                         'rows': len(result.rows) if result else None})
        if error is None:
            return 'executed', result
        refiner = constant('mac_sql_official', 'core/const.py', 'refiner_template').replace('SQLite', 'BigQuery')
        # Source add_prefix is retained even though it is imperfect for CTEs.
        prompt_sql = sql if sql.startswith(('SELECT', 'select')) else 'SELECT' + sql
        prompt = refiner.format(query=question, evidence=evidence, desc_str=desc,
                                fk_str=fk_text, sql=prompt_sql,
                                sqlite_error=error, exception_class=exception_class)
        corrected = _sql(self.model.generate('mac.refiner', prompt)[0]['content'])
        attempts.append({'stage': 'correction', 'sql': corrected})
        message.update(pred=corrected, fixed=True, send_to='Refiner')
        return 'corrected_unexecuted', None
