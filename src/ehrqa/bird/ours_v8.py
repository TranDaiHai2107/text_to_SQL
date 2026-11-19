"""Ours v8 on BIRD: the baseline's reasoning prompt as generator, plus Ours' layers.

Motivation (tuning split, v6/v7): JSON-only stages without reasoning and a heavy
requirement/plan payload made candidates agree on systematically wrong SQL; the literature
also reports little or negative value from schema linking/decomposition for gpt-4o-mini.
v8 keeps the generator prompt identical to the baseline (OmniSQL ``input_seq``: schema with
descriptions and example values, evidence, question, step-by-step instruction, final ```sql
fence) and adds, each switchable for ablation:

  values    stored values matching the question (Ours' value retrieval layer)
  fewshot   3 BM25 demonstrations from BIRD train (Ours' example layer)
  repair    execution-feedback repair of the greedy candidate (error or empty result)
  vote      execution-result vote over greedy + sampled candidates, counting only
            candidates that return values
  select    listwise LLM selection only when the largest result groups tie

Gold SQL never enters a prompt. Candidate result previews (database rows) are allowed: BIRD
data is public, and the selector compares what the candidates return.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import re

from ehrqa.agentic.trace import Trace

SQL_BLOCK = re.compile(r'```sql\s*(.*?)\s*```', re.DOTALL)
MAX_TOKENS = 2048  # baseline infer.py limit


def parse_sql(text: str) -> str:
    matches = SQL_BLOCK.findall(text or '')
    return matches[-1].strip() if matches else ''


@dataclass(frozen=True)
class V8Config:
    values: bool = True
    fewshot: bool = True
    repair: bool = True
    vote: bool = True
    select: bool = True
    samples: int = 8
    temperature: float = 0.8
    max_value_hints: int = 12


def _quote_ident(name: str) -> str:
    return name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) else '`' + name + '`'


def enrich_prompt(input_seq: str, values: list[dict], examples: list[dict]) -> str:
    """Insert Ours' retrieved context before the baseline's Instructions section."""
    blocks = []
    if values:
        lines = [f"- {_quote_ident(v['table'])}.{_quote_ident(v['column'])} = '{v['code']}'" for v in values]
        blocks.append('Stored database values that match words in the question (exact stored spelling; '
                      'use one only if the question refers to it):\n' + '\n'.join(lines))
    if examples:
        shots = [f"Question: {e['question']}\nEvidence: {e['external_knowledge'] or '-'}\nSQL: {e['sql']}"
                 for e in examples]
        blocks.append('Examples from other databases (they show SQL patterns only, not this database):\n\n'
                      + '\n\n'.join(shots))
    if not blocks:
        return input_seq
    marker = '\nInstructions:\n'
    if marker not in input_seq:
        raise ValueError('Unexpected baseline prompt layout')
    head, tail = input_seq.split(marker, 1)
    return head + '\n\n' + '\n\n'.join(blocks) + '\n' + marker + tail


def repair_prompt(prompt: str, sql: str, feedback: str) -> str:
    return (prompt + '\n\nA previous attempt for this question was:\n```sql\n' + sql + '\n```\n'
            'Execution feedback: ' + feedback + '\n'
            'Reconsider the question, schema and evidence, then write a corrected SQL query. If the previous '
            'query was in fact correct, you may return it unchanged. Use the same output format.')


def _preview(result) -> str:
    rows = result.rows[:5]
    return json.dumps({'columns': result.columns, 'row_count': len(result.rows),
                       'first_rows': [[str(v)[:60] for v in r] for r in rows]}, ensure_ascii=False)


def select_prompt(prompt: str, options: list[tuple[str, str, object]]) -> str:
    listed = '\n\n'.join(f'Candidate {cid}:\n```sql\n{sql}\n```\nResult: {_preview(res)}'
                         for cid, sql, res in options)
    return (prompt.split('\nInstructions:\n', 1)[0] + '\n\nCandidate SQL queries, which return different '
            'results:\n\n' + listed + '\n\nWhich candidate answers the question correctly, returning exactly '
            'the requested information? Think step by step, then end with one line exactly in the form '
            '"Answer: <candidate id>".')


class OursV8:
    def __init__(self, database, model, *, examples=None, config: V8Config = V8Config(), log_dir=None):
        self.db, self.model, self.examples, self.config, self.log_dir = database, model, examples, config, log_dir

    def _complete(self, trace, stage, prompt, *, n=1, temperature=0.0):
        messages = [{'role': 'user', 'content': prompt}]
        if n == 1 and temperature == 0.0:
            result = self.model.complete_text(stage, messages, MAX_TOKENS)
            contents = [result['content']]
        else:
            result = self.model.sample_text(stage, messages, MAX_TOKENS, n=n, temperature=temperature)
            contents = result['contents']
        trace.emit('model.response', operation=stage, n=n, temperature=temperature,
                   **{k: v for k, v in result.items() if k not in ('content', 'contents')}, output=contents)
        return contents

    def _execute(self, sql):
        if not sql:
            return None, 'No SQL query was found in the answer.'
        try:
            return self.db.execute(sql), None
        except ValueError as error:
            return None, str(error)[:500]

    def run(self, question: str, evidence: str, input_seq: str, *, query_id=None) -> dict:
        trace = Trace(self.log_dir, query_id=query_id)
        cfg = self.config
        calls = 0
        retrieval_text = question + ' ' + (evidence or '')
        values = self.db.catalog_search(retrieval_text, [])[:cfg.max_value_hints] if cfg.values else []
        shots = self.examples(retrieval_text)['items'] if cfg.fewshot and self.examples else []
        prompt = enrich_prompt(input_seq, values, shots)
        trace.emit('ours.context', values=[v['id'] for v in values], examples=[e['question'] for e in shots])

        jobs = [('greedy', lambda: self._complete(trace, 'generate', prompt))]
        if cfg.vote and cfg.samples:
            jobs.append(('samples', lambda: self._complete(trace, 'generate_samples', prompt,
                                                          n=cfg.samples, temperature=cfg.temperature)))
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            outputs = dict(zip([k for k, _ in jobs], pool.map(lambda job: job[1](), jobs)))
        calls += len(jobs)
        candidates = [{'id': 'g', 'sql': parse_sql(outputs['greedy'][0])}]
        candidates += [{'id': f's{i + 1}', 'sql': parse_sql(t)} for i, t in enumerate(outputs.get('samples', []))]
        for c in candidates:
            c['result'], c['error'] = self._execute(c['sql'])

        def has_values(c):
            return c['result'] is not None and any(v is not None for row in c['result'].rows for v in row)

        greedy = candidates[0]
        if cfg.repair and not has_values(greedy):
            feedback = greedy['error'] or 'The query executed but returned no rows (or only NULL values).'
            fixed = parse_sql(self._complete(trace, 'repair', repair_prompt(prompt, greedy['sql'], feedback))[0])
            calls += 1
            if fixed and fixed != greedy['sql']:
                result, error = self._execute(fixed)
                repaired = {'id': 'gr', 'sql': fixed, 'result': result, 'error': error}
                candidates.append(repaired)
                trace.emit('ours.repair', feedback=feedback[:300], sql=fixed, error=error)

        executed = [c for c in candidates if c['result'] is not None]
        if not cfg.vote:
            chosen = next((c for c in reversed(candidates[:1] + [c for c in candidates if c['id'] == 'gr'])
                           if c['result'] is not None), greedy)
            return self._finish(trace, chosen, candidates, calls, 'greedy_with_repair')
        pool_ = [c for c in executed if has_values(c)] or executed
        if not pool_:
            return self._finish(trace, greedy, candidates, calls, 'no_executable_candidate')
        groups = {}
        for c in pool_:
            groups.setdefault(c['result'].fingerprint(), []).append(c)
        ranked = sorted(groups.values(), key=len, reverse=True)
        top = [g for g in ranked if len(g) == len(ranked[0])]
        trace.emit('ours.vote', groups=[[c['id'] for c in g] for g in ranked])
        if len(top) == 1:
            return self._finish(trace, top[0][0], candidates, calls, f'vote_{len(top[0])}_of_{len(pool_)}')
        reps = [g[0] for g in top][:6]
        if not cfg.select:
            return self._finish(trace, reps[0], candidates, calls, 'tie_first')
        options = [(str(i + 1), c['sql'], c['result']) for i, c in enumerate(reps)]
        text = self._complete(trace, 'select', select_prompt(prompt, options))[0]
        calls += 1
        match = re.findall(r'Answer:\s*(?:Candidate\s*)?(\d+)', text or '')
        index = int(match[-1]) - 1 if match else -1
        if 0 <= index < len(reps):
            return self._finish(trace, reps[index], candidates, calls, f'tie_selected_{len(reps)}')
        return self._finish(trace, reps[0], candidates, calls, 'tie_select_fallback')

    def _finish(self, trace, chosen, candidates, calls, how):
        trace.emit('pipeline.final', sql=chosen['sql'], method=how, model_calls=calls)
        return {'status': 'answered' if chosen['result'] is not None else 'unresolved', 'sql': chosen['sql'],
                'reason': how, 'model_calls': calls, 'selected': {'id': chosen['id']},
                'candidates': [{'id': c['id'], 'status': 'executed' if c['result'] is not None else 'failed',
                                'sql': c['sql']} for c in candidates],
                'fallbacks': [], 'trace': trace.events, 'trace_path': str(trace.path) if trace.path else None,
                'prompt_version': 'bird_ours_v8_20261119'}
