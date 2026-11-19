"""Pure SDE-SQL three-vote judge port; transport must preserve n=3 semantics."""
from __future__ import annotations

import json
import re

from ..source_templates import constant


def _parse_vote(text: str) -> dict:
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.I | re.S)
    raw = match.group(1) if match else text.strip()
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def native_three_vote_judge(model, *, question: str, sql: str,
                            evidence: str, result_columns: tuple[str, ...]) -> dict:
    """Mirror refine_new.judge_target: >=2 modifications choose last modified SQL."""
    template = constant('sde_sql_official', 'src/judge.py',
                        'judge_target_prompt_template')
    prompt = template.format(question=question, sql=sql, evidence=evidence,
                             result=str(list(result_columns)))
    replies = model.generate('sde.judge', prompt, n=3)
    if len(replies) != 3:
        raise ValueError('Native SDE judge requires exactly three responses')
    votes = []
    for reply in replies:
        try:
            votes.append(_parse_vote(reply['content']))
        except ValueError:
            votes.append({})  # Native parse_json treats malformed JSON as an empty vote.
    changed = [vote.get('Final SQL') for vote in votes if vote.get('Modification') == 'True']
    if any(not isinstance(sql, str) or not sql.strip() for sql in changed):
        raise ValueError('SDE judge vote lacks modified SQL')
    final = changed[-1] if len(changed) >= 2 else sql
    return {'sql': final, 'modification_votes': len(changed),
            'modified': len(changed) >= 2}
