"""BigQuery/English configuration for the existing full-agentic pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import re
from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import traverse_scope

from ehrqa.agentic.pipeline import Config, FullAgentic
from ehrqa.agentic.retrieval import SequentialRAG
from ehrqa.agentic.schema import Schema
from ehrqa.agentic.database import QueryResult
from .execution_errors import IncompleteResultError


PROPOSED_VERSION = 'clinsql_ours_v1'


def ungrounded_clinical_literals(sql, question, records):
    """Flag code literals without dictionary evidence or an explicit question mention."""
    tree = parse_one(sql, read='bigquery')
    tables = {table.name for table in tree.find_all(exp.Table)}
    diagnosis = bool(tables & {'diagnoses_icd', 'd_icd_diagnoses'})
    procedure = bool(tables & {'procedures_icd', 'd_icd_procedures'})
    lab = bool(tables & {'labevents', 'd_labitems'})
    icu = bool(tables & {'chartevents', 'inputevents', 'outputevents', 'datetimeevents',
                         'procedureevents', 'ingredientevents', 'd_items'})
    expected = {'icd_code': ('d_icd_diagnoses' if diagnosis else 'd_icd_procedures')
                if diagnosis != procedure else None,
                'itemid': ('d_labitems' if lab else 'd_items') if lab != icu else None}
    errors = []
    for predicate in tree.find_all(exp.EQ, exp.In, exp.Like):
        column = predicate.this
        values = predicate.expressions if isinstance(predicate, exp.In) else [predicate.expression]
        if isinstance(predicate, exp.EQ) and isinstance(predicate.expression, exp.Column):
            column, values = predicate.expression, [predicate.this]
        if not isinstance(column, exp.Column) or column.name.lower() not in {'itemid', 'icd_code'}:
            continue
        for value in values:
            if not isinstance(value, exp.Literal):
                continue
            literal = str(value.this)
            explicit = re.search(r'\b(?:icd(?:[- ]?(?:9|10))?(?:\s+code)?|code)\s*[:=#]?\s*'
                                 + re.escape(literal) + r'(?!\w)', question, re.I)
            if column.name.lower() == 'itemid':
                explicit = re.search(r'\bitem\s*id\s*[:=#]?\s*' + re.escape(literal) + r'\b', question, re.I)
            if explicit or any(row.get('code_column') == column.name.lower()
                               and expected[column.name.lower()] in (None, row.get('table'))
                               and str(row.get('code')).casefold() == literal.casefold() for row in records):
                continue
            errors.append(f'No evidence for {column.name} filter {literal}')
    return errors


def ungrounded_join_keys(sql, schema):
    findings = []
    for scope in traverse_scope(parse_one(sql, read='bigquery')):
        for join in scope.expression.args.get('joins') or ():
            condition = join.args.get('on')
            if condition is None:
                continue
            for eq in condition.find_all(exp.EQ):
                left, right = eq.this, eq.expression
                if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                    continue
                if not left.table or not right.table or left.table == right.table:
                    continue
                source_left = scope.sources.get(left.table)
                source_right = scope.sources.get(right.table)
                if isinstance(source_left, exp.Table) and isinstance(source_right, exp.Table):
                    a, b = f'{source_left.name}.{left.name}', f'{source_right.name}.{right.name}'
                    if not schema.has_edge(a, b):
                        findings.append(f'No declared relationship for {a} = {b}')
    return findings


@dataclass(frozen=True)
class ProposedFlags:
    base_prompt_only: bool = False
    schema_rag: bool = True
    multi_layer_rag: bool = True
    sql_validation: bool = True
    self_correction: bool = True
    requirement_verification: bool = True

    def __post_init__(self):
        if self.base_prompt_only and any(asdict(self)[name] for name in (
                'schema_rag', 'multi_layer_rag', 'self_correction', 'requirement_verification')):
            raise ValueError('Base prompting requires retrieval, correction and verification disabled')
        if self.requirement_verification and not self.sql_validation:
            raise ValueError('Requirement verification needs SQL evidence from validation')


class PipelineDatabase:
    def __init__(self, adapter):
        self.adapter = adapter
        self.schema = Schema.from_records(adapter.schema_metadata(), dialect='bigquery')

    def execute(self, sql, question=''):
        dry_run = self.adapter.dry_run(sql)
        if not dry_run.valid:
            raise ValueError('GoogleSQL dry run rejected query')
        result = self.adapter.execute(sql)
        if not result.complete:
            raise IncompleteResultError('Incomplete BigQuery result')
        return QueryResult(list(result.columns), list(result.rows), result.complete,
                           result.column_types, result.job_id)

    def catalog_search(self, question, tables, limit=24):
        return []  # No patient data or clinical values sent to the LLM before policy approval.

    def requirement_findings(self, sql, question, records):
        return (ungrounded_clinical_literals(sql, question, records)
                + ungrounded_join_keys(sql, self.schema))


# Event tables imply the dictionary that grounds their codes. Retrieval is
# question-generic; no concept-specific aliases or codes are supplied here.
DICTIONARY_FOR_TABLE = {
    'd_icd_diagnoses': 'd_icd_diagnoses', 'diagnoses_icd': 'd_icd_diagnoses',
    'd_icd_procedures': 'd_icd_procedures', 'procedures_icd': 'd_icd_procedures',
    'd_labitems': 'd_labitems', 'labevents': 'd_labitems',
    'd_items': 'd_items', 'chartevents': 'd_items', 'inputevents': 'd_items',
    'outputevents': 'd_items', 'procedureevents': 'd_items', 'datetimeevents': 'd_items',
    'ingredientevents': 'd_items',
}
CATALOG_LIMIT = 24


def dictionary_search(icd_catalog, question, context, *, limit=CATALOG_LIMIT):
    """Share the evidence budget across dictionaries implied by the retrieved schema.

    A single global top-k lets one large dictionary (ICD diagnoses) fill every
    slot, so procedure or lab evidence is never shown. Each implied dictionary
    is searched separately and merged round-robin; unused slots flow to the
    dictionaries that still have candidates.
    """
    tables = []
    for table in context.get('tables', ()):
        dictionary = DICTIONARY_FOR_TABLE.get(table)
        if dictionary and dictionary not in tables:
            tables.append(dictionary)
    if not tables or 'table' not in inspect.signature(icd_catalog.search).parameters:
        return icd_catalog.search(question, context)
    # The unfiltered ranking keeps evidence for dictionaries the schema step missed.
    ranked = [*(icd_catalog.search(question, context, table=table, limit=limit) for table in tables),
              icd_catalog.search(question, context, limit=limit)]
    merged, seen = [], set()
    for position in range(limit):
        for rows in ranked:
            if position < len(rows) and len(merged) < limit and rows[position]['id'] not in seen:
                seen.add(rows[position]['id'])
                merged.append(rows[position])
    return merged


def _schema_context(index, schema, question):
    entries = index.retrieve(question)
    tables = [entry['table'] for entry in entries]
    terms = set(re.findall(r'[a-z0-9]+', question.casefold()))
    columns = {table: sorted(column for column in schema.tables[table]
                             if terms.intersection(column.split('_'))) for table in tables}
    for edge in schema.edges:
        for ref in (edge['left'], edge['right']):
            table, column = ref.split('.')
            if table in columns and column not in columns[table]:
                columns[table].append(column)
    return {'tables': tables, 'columns': columns, 'schema_sha256': index.index['schema_sha256'],
            'index_sha256': index.index['sha256']}


def build_pipeline(adapter, model, *, log_dir=None, few_shot_index=None, icd_catalog=None,
                   schema_index=None, flags=ProposedFlags(), procedure_grounding=None):
    db = PipelineDatabase(adapter)
    if schema_index is not None:
        expected = schema_index.index['schema_sha256']
        actual = {row['table']: (row.get('dataset'), row['ddl'], row.get('schema_sha256'))
                  for row in adapter.schema_metadata()}
        pinned = {row['table']: (row['dataset'], row['ddl'], expected)
                  for row in schema_index.schema_records()}
        if actual != pinned:
            raise ValueError('Pipeline schema does not match pinned Schema RAG index')
    schema_callback = ((lambda question: _schema_context(schema_index, db.schema, question))
                       if schema_index is not None else None)
    def examples(question, *, query_id=None):
        if few_shot_index is not None:
            return few_shot_index.retrieve(question, query_id=query_id)
        return {'items': [], 'found': False, 'few_shot_count': 3, 'source': 'no_approved_examples'}
    def catalog(question, context):
        rows = [row for row in dictionary_search(icd_catalog, question, context)
                if db.schema.has_ref(f"{row['table']}.{row['column']}")
                and db.schema.has_ref(f"{row['table']}.{row['code_column']}")]
        return rows

    return FullAgentic(db, SequentialRAG(db, examples, schema_callback=schema_callback,
                                       catalog_callback=catalog if icd_catalog is not None else None), model,
                       Config(profile='clinsql', log_dir=log_dir, **asdict(flags),
                              run_version=PROPOSED_VERSION), procedure_grounding=procedure_grounding)
