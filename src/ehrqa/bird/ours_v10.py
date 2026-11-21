"""Ours v10 on BIRD: v9 plus literature-backed parts, each switchable for ablation (not yet run).

Sources and why each part (see reports/Cải thiện Ours BIRD tăng mẫu.md):

  value_check   draft-guided literal check (E-SQL "candidate predicate generation", arXiv 2409.16751:
                -2.02 EX on gpt-4o-mini when removed). String literals compared with a column
                (=, LIKE, IN) are looked up in the stored values of that column; a literal that is not
                stored is reported, with similar stored values, to the greedy repair. This also catches
                aggregates over a wrong literal (COUNT = 0 "returns values", so v9 never repaired it).
  value_filter  the vote prefers candidates without such a literal (falls back to all), a free,
                deterministic tier on top of v9's "returns values" preference.
  resolve       how a vote without a majority is resolved:
                'listwise' v9's sampled listwise selector over the top groups;
                'pairwise' DeepEye-SQL style (arXiv 2510.17586): only the top-2 groups, judged in both
                           orders (position bias), ``pair_samples`` judgments per order, score =
                           group share x win rate;
                'merge'    CSC-SQL style (arXiv 2505.13271): the top-2 groups are shown together and the
                           model writes the final SQL (one of them or a corrected combination).
  dc_samples    a third generator, divide-and-conquer CoT (CHASE-SQL, arXiv 2410.01943). Budget-neutral
                variants move samples from the plan generator instead of adding new ones.
  early_stop_share  cost: when greedy + base samples already agree at this share, the plan/dc
                generators are skipped (Adaptive-Consistency / early-stopping self-consistency).

Defaults keep v9's generators (17 candidates) and turn on value_check, value_filter and the
pairwise resolver. Every choice is to be screened on the 300-question tuning split first and
confirmed once on the 1234 held-out questions. Gold SQL never enters a prompt.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import re

from ehrqa.agentic.trace import Trace
from ehrqa.bird.ours_v8 import enrich_prompt, parse_sql, repair_prompt
from ehrqa.bird.ours_v9 import (MARKER, OursV9, V9Config, has_values, needs_selection, parse_choice, plan_prompt,
                                select_prompt, set_fingerprint)
from ehrqa.bird.values import STOP, words

PROMPT_VERSION = 'bird_ours_v10_20261121'
RESOLVERS = ('listwise', 'pairwise', 'merge')
VOTE_RULES = ('ours', 'author')

DC_INSTRUCTIONS = """Instructions:
Solve the question by divide and conquer. Write each step out briefly, then give the final SQL.
1. Divide: split the question into simple sub-questions (a filter, a join, an aggregate, a ranking), each answerable by one small query.
2. Conquer: write the SQL for each sub-question, checking the columns, the stored values and every external-knowledge statement.
3. Combine: assemble the sub-queries into one query (joins, subqueries or CTEs), then simplify it by removing unneeded joins and nesting.
4. Check: the SELECT list returns exactly the information asked, in the order the question mentions it; no helper columns and never SELECT *.

Output Format:
In your answer, please enclose the generated SQL query in a code block:
```sql
-- Your SQL query
```
"""

_IDENT = r'(?:`[^`]+`|"[^"]+"|\[[^\]]+\]|[A-Za-z_]\w*)'
_STR = r"'(?:[^']|'')*'"
_CMP = re.compile(rf'(?:{_IDENT}\s*\.\s*)?({_IDENT})\s+?(NOT\s+)?(==|=|LIKE|IN)\s*'
                  rf'(\(\s*{_STR}(?:\s*,\s*{_STR})*\s*\)|{_STR})', re.I)
_CMP_TIGHT = re.compile(rf'(?:{_IDENT}\s*\.\s*)?({_IDENT})\s*(NOT\s+)?(==|=)\s*({_STR})', re.I)
_TABLES = re.compile(rf'\b(?:FROM|JOIN)\s+({_IDENT})', re.I)


def dc_prompt(prompt: str) -> str:
    if MARKER not in prompt:
        raise ValueError('Unexpected baseline prompt layout')
    return prompt.split(MARKER, 1)[0] + '\n\n' + DC_INSTRUCTIONS


def _strip(name: str) -> str:
    return name.strip('`"[]')


def _like(pattern: str, value: str) -> bool:
    """SQLite LIKE: case-insensitive, % any run, _ one character."""
    rx = ''.join('.*' if ch == '%' else '.' if ch == '_' else re.escape(ch) for ch in pattern)
    return re.fullmatch(rx, str(value), re.I | re.S) is not None


def similar_values(literal: str, values, k: int = 5) -> list[str]:
    target = literal.strip('%_').casefold()
    lw = set(words(target)) - STOP
    scored = []
    for v in values:
        g = str(v).casefold()
        if g == target:
            s = 3.0
        elif target and (target in g or g in target):
            s = 2.0
        else:
            overlap = len(lw & set(words(g)))
            if not overlap:
                continue
            s = 1.0 + overlap / (len(lw) + 1)
        scored.append((-s, len(str(v)), str(v)))
    return [v for *_, v in sorted(scored)[:k]]


def literal_mismatches(sql: str, index) -> list[dict]:
    """String literals compared (=, LIKE, IN) with an indexed text column but not stored in it.

    Columns are resolved by name within the tables the query mentions (alias prefixes ignored);
    a literal counts as stored if any such table's column holds it. Unindexed columns (numeric,
    free text, > 50k distinct values) are never reported, so the check errs towards silence."""
    if not sql:
        return []
    mentioned = {_strip(t).lower() for t in _TABLES.findall(sql)}
    found, seen = [], set()
    for match in list(_CMP.finditer(sql)) + list(_CMP_TIGHT.finditer(sql)):
        column, negated, op, rhs = match.group(1), match.group(2), match.group(3).upper(), match.group(4)
        if negated or (column.upper() in {'AND', 'OR', 'NOT', 'WHEN', 'THEN', 'ELSE', 'WHERE', 'ON', 'IS'}):
            continue
        column = _strip(column)
        tables = [t for t in index.indexed_tables(column) if not mentioned or t in mentioned]
        stores = [index.column_values(t, column) for t in tables]
        stores = [s for s in stores if s is not None]
        if not stores:
            continue
        literals = [x.replace("''", "'") for x in re.findall(r"'((?:[^']|'')*)'", rhs)]
        for lit in literals:
            key = (column.lower(), op, lit)
            if key in seen:
                continue
            seen.add(key)
            if op == 'LIKE':
                ok = any(_like(lit, v) for s in stores for v in s)
            else:
                ok = any(lit in s for s in stores)
            if not ok:
                pool = [v for s in stores for v in s]
                found.append({'column': f'{tables[0]}.{column}' if len(tables) == 1 else column, 'op': op,
                              'literal': lit, 'similar': similar_values(lit, pool)})
    return found


def mismatch_feedback(mismatches: list[dict]) -> str:
    lines = []
    for m in mismatches[:6]:
        similar = ', '.join(f"'{v}'" for v in m['similar']) or 'none found'
        lines.append(f"- {m['column']} {m['op']} '{m['literal']}': this value is not stored in that column "
                     f"(similar stored values: {similar})")
    return ('The query compares columns with values that are not stored in the database:\n' + '\n'.join(lines)
            + '\nUse the exact stored spelling, or a different column if the value belongs elsewhere.')


def vote_groups_v10(candidates: list[dict], *, use_set: bool = True, prefer_clean: bool = True) -> list[list[dict]]:
    """v9's vote with one more tier: among value-returning candidates, prefer those without a
    literal mismatch (falls back to all). Ties keep first-seen order."""
    executed = [c for c in candidates if c.get('rows') is not None]
    pool = [c for c in executed if has_values(c['rows'])] or executed
    if prefer_clean:
        pool = [c for c in pool if not c.get('mismatch')] or pool
    groups: dict[str, list[dict]] = {}
    for c in pool:
        key = set_fingerprint(c['rows']) if use_set else c['fp_multiset']
        groups.setdefault(key, []).append(c)
    return sorted(groups.values(), key=len, reverse=True)


def author_groups(candidates: list[dict]) -> list[list[dict]]:
    """OmniSQL major_voting(): every executed SQL votes, empty results included; groups by the result
    set; sorted() is stable, so ties keep the first-seen group like the author's max()."""
    groups: dict[str, list[dict]] = {}
    for c in candidates:
        if c.get('rows') is not None:
            groups.setdefault(set_fingerprint(c['rows']), []).append(c)
    return sorted(groups.values(), key=len, reverse=True)


def merge_prompt(prompt: str, a: dict, b: dict) -> str:
    listing = select_prompt(prompt, [a, b]).split('Candidate SQL queries for this question. They return different '
                                                  'results:\n\n', 1)[1].split('\n\nDecide which candidate', 1)[0]
    return (prompt.split(MARKER, 1)[0] + '\n\nTwo candidate SQL queries for this question return different results:'
            '\n\n' + listing + '\n\nCompare them: find each place where they differ (selected columns, conditions '
            'and stored values, joins, aggregation, ordering, limits) and decide which choice the question and the '
            'external knowledge require. Then write the final SQL query; it may be one of the candidates unchanged or '
            'a corrected combination of both.\n\nOutput Format:\nIn your answer, please enclose the generated SQL '
            'query in a code block:\n```sql\n-- Your SQL query\n```\n')


@dataclass(frozen=True)
class V10Config(V9Config):
    value_check: bool = True
    value_filter: bool = True
    resolve: str = 'pairwise'
    pair_samples: int = 3
    dc_samples: int = 0
    early_stop_share: float = 0.0  # 0 = off
    vote_rule: str = 'ours'  # 'author': OmniSQL major_voting (empty results vote too)
    vote_greedy: bool = True  # False: greedy and its repair are kept out of the vote (OmniSQL Maj-8)

    def __post_init__(self):
        if self.resolve not in RESOLVERS:
            raise ValueError(f'resolve must be one of {RESOLVERS}')
        if self.vote_rule not in VOTE_RULES:
            raise ValueError(f'vote_rule must be one of {VOTE_RULES}')


class OursV10(OursV9):
    def __init__(self, database, model, *, examples=None, config: V10Config = V10Config(), log_dir=None):
        super().__init__(database, model, examples=examples, config=config, log_dir=log_dir)

    def _check(self, c):
        cfg = self.config
        c['mismatch'] = (literal_mismatches(c['sql'], self.db.values)
                         if (cfg.value_check or cfg.value_filter) and c.get('rows') is not None else [])
        return c

    def _groups(self, candidates):
        cfg = self.config
        pool = candidates if cfg.vote_greedy else [c for c in candidates if c['id'] not in ('g', 'gr')]
        if cfg.vote_rule == 'author':
            return author_groups(pool)
        return vote_groups_v10(pool, use_set=cfg.set_vote, prefer_clean=cfg.value_filter)

    def _generate(self, trace, jobs):
        if not jobs:
            return {}
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            return dict(zip([k for k, _ in jobs], pool.map(lambda job: job[1](), jobs)))

    def run(self, question: str, evidence: str, input_seq: str, *, query_id=None) -> dict:
        trace = Trace(self.log_dir, query_id=query_id)
        cfg = self.config
        retrieval_text = question + ' ' + (evidence or '')
        values = self.db.catalog_search(retrieval_text, [])[:cfg.max_value_hints] if cfg.values else []
        shots = self.examples(retrieval_text)['items'] if cfg.fewshot and self.examples else []
        prompt = enrich_prompt(input_seq, values, shots)
        trace.emit('ours.context', values=[v['id'] for v in values], examples=[e['question'] for e in shots])

        sample = lambda stage, text, n: (lambda: self._complete(trace, stage, text, n=n, temperature=cfg.temperature))
        first = [('g', lambda: self._complete(trace, 'generate', prompt))]
        if cfg.base_samples:
            first.append(('s', sample('generate_samples', prompt, cfg.base_samples)))
        later = []
        if cfg.plan_samples:
            later.append(('p', sample('generate_plan_samples', plan_prompt(prompt), cfg.plan_samples)))
        if cfg.dc_samples:
            later.append(('d', sample('generate_dc_samples', dc_prompt(prompt), cfg.dc_samples)))

        def build(outputs, prefixes):
            out = []
            for prefix in prefixes:
                texts = outputs.get(prefix, [])
                if prefix == 'g':
                    out.append({'id': 'g', 'sql': parse_sql(texts[0])})
                else:
                    out += [{'id': f'{prefix}{i + 1}', 'sql': parse_sql(t)} for i, t in enumerate(texts)]
            return [self._check(self._execute(c)) for c in out]

        early = cfg.early_stop_share > 0 and bool(later)
        outputs = self._generate(trace, first if early else first + later)
        calls = len(outputs)
        candidates = build(outputs, ['g', 's'] if early else ['g', 's', 'p', 'd'])
        if early:
            groups = self._groups(candidates)
            share = len(groups[0]) / len(candidates) if groups else 0.0
            if share >= cfg.early_stop_share:
                trace.emit('ours.early_stop', share=round(share, 3), skipped=[k for k, _ in later])
            else:
                more = self._generate(trace, later)
                calls += len(more)
                candidates += build(more, ['p', 'd'])

        greedy = candidates[0]
        failed_or_empty = not (greedy['rows'] is not None and has_values(greedy['rows']))
        mismatched = cfg.value_check and bool(greedy.get('mismatch'))
        if cfg.repair and (failed_or_empty or mismatched):
            if failed_or_empty:
                feedback = greedy['error'] or 'The query executed but returned no rows (or only NULL values).'
                if mismatched:
                    feedback += '\n' + mismatch_feedback(greedy['mismatch'])
            else:
                feedback = mismatch_feedback(greedy['mismatch'])
            fixed = parse_sql(self._complete(trace, 'repair', repair_prompt(prompt, greedy['sql'], feedback))[0])
            calls += 1
            if fixed and fixed != greedy['sql']:
                repaired = self._check(self._execute({'id': 'gr', 'sql': fixed}))
                candidates.append(repaired)
                trace.emit('ours.repair', feedback=feedback[:500], sql=fixed, error=repaired['error'],
                           trigger='value_mismatch' if not failed_or_empty else 'failed_or_empty')

        groups = self._groups(candidates)
        trace.emit('ours.vote', groups=[[c['id'] for c in g] for g in groups],
                   mismatched=[c['id'] for c in candidates if c.get('mismatch')])
        if not groups:  # nothing executed: the greedy SQL (or the first sample when greedy does not vote)
            fallback = greedy if cfg.vote_greedy or len(candidates) == 1 else candidates[1]
            return self._finish(trace, fallback, candidates, calls, 'no_executable_candidate')
        total = sum(len(g) for g in groups)
        how = f'vote_{len(groups[0])}_of_{total}'
        if not (cfg.select and needs_selection(groups, cfg.select_below)):
            return self._finish(trace, groups[0][0], candidates, calls, how)
        resolver = {'listwise': self._listwise, 'pairwise': self._pairwise, 'merge': self._merge}[cfg.resolve]
        chosen, suffix, used = resolver(trace, prompt, groups, total, candidates)
        return self._finish(trace, chosen, candidates, calls + used, how + suffix)

    # ---- resolvers: (chosen candidate, reason suffix, model calls used) ----
    def _options(self, reps):
        return [{'id': str(i + 1), 'sql': c['sql'], 'rows': c['rows'], 'columns': c['columns']}
                for i, c in enumerate(reps)]

    def _listwise(self, trace, prompt, groups, total, candidates):
        cfg = self.config
        reps = [g[0] for g in groups[:cfg.select_groups]]
        options = self._options(reps)
        ids = [o['id'] for o in options]
        texts = self._complete(trace, 'select', select_prompt(prompt, options), n=cfg.select_samples,
                               temperature=cfg.temperature) if cfg.select_samples > 1 else \
            self._complete(trace, 'select', select_prompt(prompt, options))
        votes = [v for v in (parse_choice(t, ids) for t in texts) if v]
        choice = max(ids, key=lambda x: (votes.count(x), -ids.index(x))) if votes else None
        trace.emit('ours.select', resolver='listwise', options=[c['id'] for c in reps], votes=votes, choice=choice)
        if choice is None:
            return reps[0], '_select_fallback', 1
        return reps[int(choice) - 1], f'_selected_{len(reps)}', 1

    def _pairwise(self, trace, prompt, groups, total, candidates):
        cfg = self.config
        a, b = groups[0][0], groups[1][0]
        share = {'a': len(groups[0]) / total, 'b': len(groups[1]) / total}
        orders = [('a', 'b'), ('b', 'a')]
        reps = {'a': a, 'b': b}

        def judge(order):
            options = self._options([reps[order[0]], reps[order[1]]])
            texts = self._complete(trace, 'select_pair', select_prompt(prompt, options), n=cfg.pair_samples,
                                   temperature=cfg.temperature)
            picks = [parse_choice(t, ['1', '2']) for t in texts]
            return [order[int(p) - 1] for p in picks if p]

        with ThreadPoolExecutor(max_workers=2) as pool:
            votes = [v for vs in pool.map(judge, orders) for v in vs]
        if not votes:
            trace.emit('ours.select', resolver='pairwise', options=[a['id'], b['id']], votes=[], choice=None)
            return a, '_pair_fallback', 2
        score = {k: share[k] * votes.count(k) / len(votes) for k in ('a', 'b')}
        winner = 'b' if score['b'] > score['a'] else 'a'
        trace.emit('ours.select', resolver='pairwise', options=[a['id'], b['id']], votes=votes,
                   score={k: round(v, 3) for k, v in score.items()}, choice=reps[winner]['id'])
        return reps[winner], f'_pair_{winner}', 2

    def _merge(self, trace, prompt, groups, total, candidates):
        a, b = groups[0][0], groups[1][0]
        options = self._options([a, b])
        sql = parse_sql(self._complete(trace, 'merge', merge_prompt(prompt, options[0], options[1]))[0])
        merged = self._check(self._execute({'id': 'm', 'sql': sql}))
        if merged['rows'] is None or not has_values(merged['rows']):
            trace.emit('ours.merge', sql=sql, error=merged['error'], choice=a['id'])
            return a, '_merge_fallback', 1
        fp = set_fingerprint(merged['rows'])
        for g in groups:
            if set_fingerprint(g[0]['rows']) == fp:
                trace.emit('ours.merge', sql=sql, agrees_with=g[0]['id'], choice=g[0]['id'])
                return g[0], f"_merge_agrees_{g[0]['id']}", 1
        candidates.append(merged)
        trace.emit('ours.merge', sql=sql, agrees_with=None, choice='m')
        return merged, '_merge_new', 1

    def _finish(self, trace, chosen, candidates, calls, how):
        out = super()._finish(trace, chosen, candidates, calls, how)
        out['prompt_version'] = PROMPT_VERSION
        return out
