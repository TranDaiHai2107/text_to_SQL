"""SDE-SQL exploration, execution consistency and refinement on BigQuery."""
from __future__ import annotations

import json
import hashlib
import re
from collections.abc import Mapping

from ..chat_multi_provider import OpenAIChatMultiProvider
from ..execution_errors import IncompleteResultError, SecurityRejected
from ..offline import MockBigQuery
from ..source_templates import constant, isolated_function
from .sde_judge import native_three_vote_judge
from .sde_refine_policy import native_refinement_reason
from .sde_subqueries import timed_bigquery_get_subsqls


def _freeze(value):
    """Make nested BigQuery values comparable without storing their raw contents."""
    if isinstance(value, Mapping) or hasattr(value, 'items'):
        return ('struct', tuple(sorted((k, _freeze(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return ('array', tuple(_freeze(v) for v in value))
    if isinstance(value, float) and value != value:
        return ('nan',)
    return value


def _most_consistent(candidates, results):
    """Native SDE rule: nonempty result-set majority, first candidate on ties."""
    groups = {}
    for sql, result in zip(candidates, results, strict=True):
        if result is None or not result.rows:
            continue
        key = frozenset(tuple(_freeze(value) for value in row) for row in result.rows)
        groups.setdefault(key, []).append(sql)
    best, count = candidates[0], 0
    for group in groups.values():
        if len(group) > count:
            best, count = group[0], len(group)
    return best


def _json_object(content: str) -> dict:
    fence = re.search(r'```(?:json)?\s*(.*?)```', content, re.I | re.S)
    raw = fence[1] if fence else content[content.find('{'):] if '{' in content else ''
    try:
        parsed, _ = json.JSONDecoder().raw_decode(raw.lstrip())
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _nonempty_sql(value):
    return isinstance(value, str) and bool(value.strip())


def _source_sql_cleanup(sql):
    return (sql.replace("|| ' ' ||", ',').replace("|| ', ' ||", ',')
            .replace('ASC LIMIT', 'ASC NULLS LAST LIMIT'))


def _dialect_template(template):
    template = re.sub(r'(?:# SQLite tricks|\[SQLite Tricks\]).*?(?=# Database admin instructions:|\[Database admin instructions\])',
                      '', template, flags=re.I | re.S)
    template = template.replace("date('now')", 'CURRENT_DATE()').replace('SQLite', 'BigQuery')
    return ('Use GoogleSQL and fully qualified table identifiers from the supplied schema.\n'
            + template)


def _generation_sql(content: str) -> str:
    text = content.strip()
    if 'final_sql_query' in text or text.startswith('{') or re.search(r'```json', text, re.I):
        text = _json_object(text).get('final_sql_query')
    else:
        fence = re.search(r'```sql\s*(.*?)```', text, re.I | re.S)
        if fence:
            text = fence[1]
    return text.strip() if _nonempty_sql(text) else ''


class SDESQL:
    def __init__(self, model, database, *, judge=None, max_refinements=3, candidates=9,
                 allow_probe_feedback=False, exploration_checkpoint=None, saved_probe=None):
        if judge is not None:
            raise ValueError('Custom Boolean judge changes native SDE three-vote selection')
        if (max_refinements, candidates) != (3, 9):
            raise ValueError('Keep source three refinements and nine-candidate self-consistency')
        transport = getattr(model, 'model', model)
        backend = database
        while hasattr(backend, 'database'):
            backend = backend.database
        self.external_transport = isinstance(transport, OpenAIChatMultiProvider)
        if self.external_transport:
            if isinstance(backend, MockBigQuery):
                raise PermissionError('SDE Chat Completions cannot use MockBigQuery probe evidence')
            if not allow_probe_feedback:
                raise PermissionError('SDE probe feedback needs separate authorization')
        self.model, self.db = model, database
        self.exploration_checkpoint = exploration_checkpoint
        self.saved_probe = saved_probe

    def _query(self, sql, *, probe=False):
        if not sql:
            return None, 'Model response did not contain a SQL query'
        try:
            dry_run = self.db.dry_run(sql)
            if not dry_run.valid:
                return None, 'BigQuery rejected the SQL during dry run'
            if probe and hasattr(self.db, 'probe_presence'):
                return self.db.probe_presence(sql), None
            result = self.db.probe(sql) if probe else self.db.execute(sql)
        except SecurityRejected:
            return None, 'SQL rejected by the read-only guard'
        except ValueError:
            return None, 'BigQuery rejected the SQL'
        if not result.complete:
            raise IncompleteResultError('Incomplete SDE SQL result')
        return result, None

    def _probes(self, sqls, attempts, *, phase, numbered=False):
        reports = []
        for index, sql in enumerate(sqls, 1):
            if not numbered:
                sql = _source_sql_cleanup(sql)
            if phase == 'explore1' and self.saved_probe and sql == self.saved_probe[0]:
                result, error = self.saved_probe[1], None
                self.saved_probe = None
            else:
                result, error = self._query(sql, probe=True)
            label = ('There are some BigQuery errors.' if error else
                     'Not NULL' if (result.has_rows if hasattr(result, 'has_rows') else result.rows) else 'NULL')
            attempts.append({'stage': 'probe', 'phase': phase, 'sql': sql, 'label': label})
            prefix = f'{index}. ' if numbered else ''
            reports.append(f'{prefix}{sql}: 【{label}】\n')
        return ''.join(reports)

    def _exploration_response(self, stage, prompt, valid_group):
        path = (self.exploration_checkpoint / f'{stage}.{hashlib.sha256(prompt.encode()).hexdigest()}.json'
                if self.exploration_checkpoint is not None else None)
        if path is not None and path.exists():
            groups = json.loads(path.read_bytes())
            if not groups or not all(valid_group(group) for group in groups.values()):
                raise ValueError('Invalid saved SDE exploration checkpoint')
            return groups
        # Initial call plus retries for the native counter range 0..5.
        for _ in range(7):
            groups = _json_object(self.model.generate(stage, prompt)[0]['content'])
            if groups and all(valid_group(group) for group in groups.values()):
                if path is not None:
                    temporary = path.with_suffix('.tmp')
                    with temporary.open('x', encoding='utf-8') as stream:
                        json.dump(groups, stream, ensure_ascii=False)
                    temporary.replace(path)
                return groups
        raise ValueError(f'{stage} exhausted its probe JSON retry limit')

    def probe_before_generation(self, question, schema_text, knowledge, match, attempts):
        first = _dialect_template(constant('sde_sql_official', 'src/explore_new.py', 'explore_prompt_1'))
        second = _dialect_template(constant('sde_sql_official', 'src/explore_new.py', 'explore_prompt_2'))
        arguments = dict(DESCRIPTION=schema_text, HINT=knowledge, QUESTION=question, MATCH=match)
        groups = self._exploration_response(
            'sde.explore1', first.format(**arguments),
            lambda group: isinstance(group, list) and all(_nonempty_sql(sql) for sql in group))
        evidence1 = ''.join(f'- {name}:\n' + self._probes(sqls, attempts, phase='explore1') + '\n'
                            for name, sqls in groups.items())
        combined = self._exploration_response(
            'sde.explore2', second.format(**arguments, PROBE_RESULTS=evidence1), _nonempty_sql)
        evidence2 = '- Combined SQL Probes:\n' + self._probes(combined.values(), attempts, phase='explore2') + '\n'
        return evidence1 + evidence2

    def run(self, question: str, *, schema_text: str, knowledge: str = '', match: str = '') -> dict:
        if self.external_transport and (knowledge or match):
            raise PermissionError('External SDE knowledge and matched values require a reviewed evidence path')
        attempts = []
        evidence = self.probe_before_generation(question, schema_text, knowledge, match, attempts)
        native_prompt = isolated_function('sde_sql_official',
                                           'src/prompt_stepv54_explore_zeroshot.py', 'prompt')
        # Pass placeholders through the native builder so dialect substitutions
        # never rewrite a clinical question, metadata or probe SQL.
        prompt = _dialect_template(native_prompt(
            '{question}', '{knowledge}', '{schema}', '{description}', '',
            '{match}', '', '{evidence}'))
        inputs = {'question': question, 'knowledge': knowledge, 'schema': '',
                  'description': schema_text, 'match': match, 'evidence': evidence}
        prompt = re.sub(r'\{(question|knowledge|schema|description|match|evidence)\}',
                        lambda match: inputs[match[1]], prompt)
        candidates = [_generation_sql(r['content']) for r in self.model.generate('sde.generate', prompt, n=9)]
        if len(candidates) != 9:
            raise ValueError('SDE generation requires exactly nine choices')
        results = []
        for sql in candidates:
            result, error = self._query(sql)
            results.append(result)
            attempts.append({'stage': 'candidate', 'sql': sql, 'error': error})
        selected = _source_sql_cleanup(_most_consistent(candidates, results))
        current = selected
        current_result, error = self._query(selected)
        attempts.append({'stage': 'refinement_execution', 'sql': selected, 'error': error})
        reason = native_refinement_reason(
            current_result.rows[:5] if current_result is not None else None,
            try_times=0, max_try_times=3)
        attempts.append({'stage': 'refinement_decision', 'sql': selected, 'reason': reason})
        if reason is None:
            decision = native_three_vote_judge(
                self.model, question=question, sql=selected, evidence=knowledge,
                result_columns=current_result.columns)
            attempts.append({'stage': 'judge', 'sql': selected,
                             'modification_votes': decision['modification_votes'],
                             'modified': decision['modified']})
            return {'sql': decision['sql'],
                    'status': 'judge_modified_unexecuted' if decision['modified'] else 'executed',
                    'attempts': attempts, 'result': None if decision['modified'] else current_result}
        # Source refine_sql performs at most three corrections. With use_check=False,
        # the outer generation loop exits after this refinement regardless of score.
        template_args = dict(database_schema=schema_text, pk_str='', fk_str='',
                             query=question, evidence=knowledge)
        for try_times in range(3):
            template_args['old_sql'] = current
            if reason != 'no data selected':
                error_prompt = _dialect_template(
                    constant('sde_sql_official', 'src/refine_new.py', 'error_result_prompt'))
                prompt = error_prompt.format(**template_args, sqlite_error=error or reason)
                stage = 'sde.refine_error'
            else:
                # Native probe_refine_sql: decompose the old SQL, probe those
                # subqueries, ask for fix probes, execute them, then refine.
                try:
                    diagnosis_sqls = timed_bigquery_get_subsqls(current)
                except ValueError:
                    search_prompt = _dialect_template(
                        constant('sde_sql_official', 'src/refine_new.py', 'search_prompt'))
                    prompt = search_prompt.format(sql=current)
                    diagnosis_sqls = self._refinement_probes('sde.search_probes', prompt)
                diagnosis = self._probes(diagnosis_sqls, attempts, phase='diagnosis', numbered=True)
                fix_probe_prompt = _dialect_template(
                    constant('sde_sql_official', 'src/refine_new.py', 'fix_probe_prompt_new'))
                prompt = fix_probe_prompt.format(**template_args, probe_results=diagnosis)
                refine_sqls = self._refinement_probes('sde.refine_probes', prompt)
                fix_diagnosis = self._probes(refine_sqls, attempts, phase='fix', numbered=True)
                refine_evidence = ('## Diagnose Probing result\n' + diagnosis +
                                   '\n## Fix Probing result\n' + fix_diagnosis)
                empty_prompt = _dialect_template(
                    constant('sde_sql_official', 'src/refine_new.py', 'empty_result_prompt'))
                prompt = empty_prompt.format(**template_args, probe_results=refine_evidence)
                stage = 'sde.refine'
            refined = _generation_sql(self.model.generate(stage, prompt)[0]['content'])
            attempts.append({'stage': 'refine', 'sql': refined})
            current = refined
            current_result, error = self._query(current)
            attempts.append({'stage': 'refinement_execution', 'sql': current, 'error': error})
            reason = native_refinement_reason(
                current_result.rows[:5] if current_result is not None else None,
                try_times=try_times + 1, max_try_times=3)
            attempts.append({'stage': 'refinement_decision', 'sql': current,
                             'reason': reason})
            if reason is None:
                break
        return {'sql': current, 'status': 'executed' if current_result is not None
                else 'unresolved', 'attempts': attempts, 'result': current_result}

    def _refinement_probes(self, stage, prompt):
        groups = _json_object(self.model.generate(stage, prompt)[0]['content'])
        if not all(_nonempty_sql(sql) for sql in groups.values()):
            raise ValueError(f'{stage} returned invalid probe SQL')
        return list(groups.values())
