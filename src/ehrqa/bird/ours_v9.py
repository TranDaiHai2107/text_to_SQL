"""Ours v9 on BIRD: v8 plus a second, plan-structured generator and a margin-gated selector.

Changes from v8 (each switchable for ablation), chosen on the 300-question tuning split:

  set_vote    candidates are grouped by the *set* of returned rows (duplicates ignored), the
              answer equivalence used by BIRD's EX metric and by the baseline's own majority
              vote; v8 grouped by the multiset, splitting DISTINCT/non-DISTINCT variants
  plan        a second generator: the same schema/evidence/question/retrieved context, but the
              instructions ask for an explicit query plan (requested outputs first, evidence,
              filters, joins, ranking, final self-check) before the SQL; sampled at T=0.8
  select      listwise LLM selection with reasoning over the largest result groups, only when no
              group holds a majority of the candidates (share < ``select_below``=0.5) or the top
              groups tie; the selector is sampled ``select_samples`` times and its choices voted
              (tuning split: above 0.5 the selector broke as many answers as it fixed)

Gold SQL never enters a prompt.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re

from ehrqa.agentic.trace import Trace
from ehrqa.bird.ours_v8 import MAX_TOKENS, enrich_prompt, parse_sql, repair_prompt

PROMPT_VERSION = 'bird_ours_v9_20261119'
MARKER = '\nInstructions:\n'

PLAN_INSTRUCTIONS = """Instructions:
Write the query by following this plan. Write each step out briefly, then give the final SQL.
1. Output: list the items the question asks to return, in the order it mentions them. Each requested item is its own column; add no helper or explanatory columns and never use SELECT *. When the question asks for values of matching rows, return those rows; use an aggregate (COUNT, SUM, AVG, MAX, ...) only when the question asks for one.
2. Evidence: apply each external-knowledge statement literally (formulas, value codes, which column to use).
3. Filters: map every condition in the question to a column and a stored value, checking spelling and case against the example values.
4. Joins: use only the tables needed, joined on the keys shown in the schema.
5. Ordering: for "highest", "lowest", "most" and similar, use ORDER BY with LIMIT unless the question asks for several items.
6. Check: re-read the question and confirm the SELECT list returns all the requested information and nothing more.

Output Format:
In your answer, please enclose the generated SQL query in a code block:
```sql
-- Your SQL query
```
"""


def plan_prompt(prompt: str) -> str:
    """The (enriched) baseline prompt with its instructions replaced by the plan instructions."""
    if MARKER not in prompt:
        raise ValueError('Unexpected baseline prompt layout')
    return prompt.split(MARKER, 1)[0] + '\n\n' + PLAN_INSTRUCTIONS


def _cell(v):
    if v is None:
        return ['null', None]
    if isinstance(v, bytes):
        return ['bytes', v.hex()]
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        try:
            return ['number', str(Decimal(str(v)).normalize())]
        except Exception:  # nan/inf
            return ['number', str(v)]
    return [type(v).__name__, str(v)]


def set_fingerprint(rows) -> str:
    """Fingerprint of the set of rows (order and duplicates ignored), like BIRD's EX."""
    unique = sorted({json.dumps([_cell(v) for v in row], ensure_ascii=False) for row in rows})
    return hashlib.sha256(json.dumps(unique, ensure_ascii=False).encode()).hexdigest()


def has_values(rows) -> bool:
    return any(v is not None for row in rows for v in row)


def _preview(rows, columns=None) -> str:
    unique = list(dict.fromkeys(tuple(r) for r in rows))
    return json.dumps({'columns': columns, 'row_count': len(rows), 'distinct_rows': len(unique),
                       'first_rows': [[str(v)[:60] for v in r] for r in unique[:5]]}, ensure_ascii=False)


def select_prompt(prompt: str, options: list[dict]) -> str:
    """options: {'id', 'sql', 'rows', 'columns'[, 'support']}; prompt is the enriched baseline prompt.

    'support' (optional) is shown as how many independently generated queries returned that result."""
    def support(o):
        return f"\nSupport: {o['support']} of the generated queries returned this result." if 'support' in o else ''
    listed = '\n\n'.join(f"Candidate {o['id']}:\n```sql\n{o['sql']}\n```\nResult: "
                         f"{_preview(o['rows'], o.get('columns'))}{support(o)}" for o in options)
    return (prompt.split(MARKER, 1)[0] + '\n\nCandidate SQL queries for this question. They return different '
            'results:\n\n' + listed + '\n\nDecide which candidate answers the question correctly. For each '
            'candidate check: (1) the SELECT list returns exactly the information asked, no more and no less; '
            '(2) every condition in the question and every external-knowledge statement is applied correctly, '
            'with the right columns and stored values; (3) joins, aggregation, ordering and limits match the '
            'question; (4) the result looks plausible. Think step by step, then end with one line exactly in '
            'the form "Answer: <candidate id>".')


def parse_choice(text: str, ids: list[str]):
    match = re.findall(r'Answer:\s*\**\s*(?:Candidate\s*)?([A-Za-z0-9]+)', text or '')
    return match[-1] if match and match[-1] in ids else None


def vote_groups(candidates: list[dict], *, use_set: bool = True) -> list[list[dict]]:
    """Group executed candidates that return values (fall back to all executed), largest first.

    Each candidate needs 'rows' (None if it failed) and 'fp_multiset' when use_set is False.
    Ties keep first-seen order (greedy first), like the baseline's max()."""
    executed = [c for c in candidates if c.get('rows') is not None]
    pool = [c for c in executed if has_values(c['rows'])] or executed
    groups: dict[str, list[dict]] = {}
    for c in pool:
        key = set_fingerprint(c['rows']) if use_set else c['fp_multiset']
        groups.setdefault(key, []).append(c)
    return sorted(groups.values(), key=len, reverse=True)


def needs_selection(groups, select_below: float) -> bool:
    if len(groups) < 2:
        return False
    total = sum(len(g) for g in groups)
    return len(groups[0]) == len(groups[1]) or len(groups[0]) / total < select_below


@dataclass(frozen=True)
class V9Config:
    values: bool = True
    fewshot: bool = True
    repair: bool = True
    set_vote: bool = True
    base_samples: int = 8
    plan_samples: int = 8
    temperature: float = 0.8
    select: bool = True
    select_below: float = 0.5
    select_groups: int = 3
    select_samples: int = 5
    max_value_hints: int = 12


class OursV9:
    def __init__(self, database, model, *, examples=None, config: V9Config = V9Config(), log_dir=None):
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

    def _execute(self, c):
        if not c['sql']:
            c['rows'], c['columns'], c['error'] = None, None, 'No SQL query was found in the answer.'
            return c
        try:
            result = self.db.execute(c['sql'])
            c['rows'], c['columns'], c['error'] = result.rows, result.columns, None
            c['fp_multiset'] = result.fingerprint()
        except ValueError as error:
            c['rows'], c['columns'], c['error'] = None, None, str(error)[:500]
        return c

    def run(self, question: str, evidence: str, input_seq: str, *, query_id=None) -> dict:
        trace = Trace(self.log_dir, query_id=query_id)
        cfg = self.config
        retrieval_text = question + ' ' + (evidence or '')
        values = self.db.catalog_search(retrieval_text, [])[:cfg.max_value_hints] if cfg.values else []
        shots = self.examples(retrieval_text)['items'] if cfg.fewshot and self.examples else []
        prompt = enrich_prompt(input_seq, values, shots)
        trace.emit('ours.context', values=[v['id'] for v in values], examples=[e['question'] for e in shots])

        jobs = [('g', lambda: self._complete(trace, 'generate', prompt))]
        if cfg.base_samples:
            jobs.append(('s', lambda: self._complete(trace, 'generate_samples', prompt,
                                                    n=cfg.base_samples, temperature=cfg.temperature)))
        if cfg.plan_samples:
            jobs.append(('p', lambda: self._complete(trace, 'generate_plan_samples', plan_prompt(prompt),
                                                    n=cfg.plan_samples, temperature=cfg.temperature)))
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            outputs = dict(zip([k for k, _ in jobs], pool.map(lambda job: job[1](), jobs)))
        calls = len(jobs)
        candidates = [{'id': 'g', 'sql': parse_sql(outputs['g'][0])}]
        for prefix in ('s', 'p'):
            candidates += [{'id': f'{prefix}{i + 1}', 'sql': parse_sql(t)} for i, t in enumerate(outputs.get(prefix, []))]
        for c in candidates:
            self._execute(c)

        greedy = candidates[0]
        if cfg.repair and not (greedy['rows'] is not None and has_values(greedy['rows'])):
            feedback = greedy['error'] or 'The query executed but returned no rows (or only NULL values).'
            fixed = parse_sql(self._complete(trace, 'repair', repair_prompt(prompt, greedy['sql'], feedback))[0])
            calls += 1
            if fixed and fixed != greedy['sql']:
                repaired = self._execute({'id': 'gr', 'sql': fixed})
                candidates.append(repaired)
                trace.emit('ours.repair', feedback=feedback[:300], sql=fixed, error=repaired['error'])

        groups = vote_groups(candidates, use_set=cfg.set_vote)
        trace.emit('ours.vote', groups=[[c['id'] for c in g] for g in groups])
        if not groups:
            return self._finish(trace, greedy, candidates, calls, 'no_executable_candidate')
        total = sum(len(g) for g in groups)
        how = f'vote_{len(groups[0])}_of_{total}'
        if not (cfg.select and needs_selection(groups, cfg.select_below)):
            return self._finish(trace, groups[0][0], candidates, calls, how)
        reps = [g[0] for g in groups[:cfg.select_groups]]
        options = [{'id': str(i + 1), 'sql': c['sql'], 'rows': c['rows'], 'columns': c['columns']}
                   for i, c in enumerate(reps)]
        ids = [o['id'] for o in options]
        if cfg.select_samples > 1:
            texts = self._complete(trace, 'select', select_prompt(prompt, options), n=cfg.select_samples,
                                   temperature=cfg.temperature)
        else:
            texts = self._complete(trace, 'select', select_prompt(prompt, options))
        calls += 1
        votes = [v for v in (parse_choice(t, ids) for t in texts) if v]
        choice = max(ids, key=lambda x: (votes.count(x), -ids.index(x))) if votes else None
        trace.emit('ours.select', options=[c['id'] for c in reps], votes=votes, choice=choice)
        if choice is None:
            return self._finish(trace, reps[0], candidates, calls, how + '_select_fallback')
        return self._finish(trace, reps[int(choice) - 1], candidates, calls, how + f'_selected_{len(reps)}')

    def _finish(self, trace, chosen, candidates, calls, how):
        trace.emit('pipeline.final', sql=chosen['sql'], method=how, model_calls=calls)
        return {'status': 'answered' if chosen.get('rows') is not None else 'unresolved', 'sql': chosen['sql'],
                'reason': how, 'model_calls': calls, 'selected': {'id': chosen['id']},
                'candidates': [{'id': c['id'], 'status': 'executed' if c.get('rows') is not None else 'failed',
                                'sql': c['sql']} for c in candidates],
                'fallbacks': [], 'trace': trace.events, 'trace_path': str(trace.path) if trace.path else None,
                'prompt_version': PROMPT_VERSION}
