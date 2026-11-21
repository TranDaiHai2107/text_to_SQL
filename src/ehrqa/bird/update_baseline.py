"""update_baseline: the OmniSQL GPT-4o-mini baseline upgraded one change at a time ("approach 1").

Rung 0 is the paper's own protocol, run with this code: the unchanged OmniSQL prompt (``input_seq``),
gpt-4o-mini-2024-07-18, 8 samples at T = 0.8 (max 2048 tokens), the author's major_voting (every
executed SQL votes, empty results too; the greedy SQL does not vote). Each later rung adds exactly one
change on top of the previous rung, so consecutive rungs form a paired ablation (McNemar on the same
1534 questions):

  ub0_baseline      OmniSQL Maj-8 protocol (reference 61.99 with the stored samples, paper 61.5)
  ub1_vote          vote rule: empty / all-NULL results only count when nothing returns values
  ub2_context       prompt context: stored values matching the question + 3 BM25 examples from BIRD train
  ub3_repair        the greedy SQL joins the vote; when it fails or returns nothing it is repaired once
                    with the execution feedback, and the repair joins the vote too
  ub4_plan          8 more samples from a query-plan prompt (same context)
  ub5_select        sampled listwise LLM selector, only when no result group holds a majority (= Ours v9)
  ub6_value_check   draft-guided literal check feeding the repair + vote tier without unstored literals
  ub7_pairwise      the no-majority case resolved pairwise over the top-2 groups (= Ours v10 default)

Rungs 0-5 are measured from stored runs with no API calls (stored baseline samples, Ours v9
candidates); see benchmarks/omnisql/experiments/update_baseline_ladder.py. Rungs 6-7 need new runs
(run_ours_bird.py --variant ub6_value_check / ub7_pairwise, tuning split first). Online, rung 0
re-samples, so it differs from the stored Maj-8 by run-to-run noise (about 0.8 EX between two draws).
"""
from __future__ import annotations

from ehrqa.bird.ours_v10 import OursV10, V10Config

# (name, change added at this rung, config overrides relative to the previous rung)
STEPS = [
    ('ub0_baseline', 'OmniSQL Maj-8 protocol', dict(
        values=False, fewshot=False, repair=False, plan_samples=0, select=False, value_check=False,
        value_filter=False, vote_rule='author', vote_greedy=False, resolve='listwise', base_samples=8)),
    ('ub1_vote', 'vote ignores empty results when others return values', dict(vote_rule='ours')),
    ('ub2_context', 'stored-value hints + BM25 few-shot in the prompt', dict(values=True, fewshot=True)),
    ('ub3_repair', 'greedy votes; execution-feedback repair of a failed/empty greedy',
     dict(vote_greedy=True, repair=True)),
    ('ub4_plan', '8 more samples from a query-plan prompt', dict(plan_samples=8)),
    ('ub5_select', 'gated listwise LLM selector (= Ours v9)', dict(select=True)),
    ('ub6_value_check', 'draft-guided literal check + vote tier', dict(value_check=True, value_filter=True)),
    ('ub7_pairwise', 'pairwise top-2 resolver (= Ours v10)', dict(resolve='pairwise')),
]
NAMES = [name for name, _, _ in STEPS]


def ladder_config(name: str) -> V10Config:
    """Cumulative config of a rung: every override up to and including it."""
    if name not in NAMES:
        raise ValueError(f'unknown rung {name}; one of {NAMES}')
    merged = {}
    for step, _, overrides in STEPS:
        merged.update(overrides)
        if step == name:
            return V10Config(**merged)


class UpdateBaseline(OursV10):
    def __init__(self, database, model, *, rung: str = 'ub7_pairwise', examples=None, log_dir=None):
        super().__init__(database, model, examples=examples, config=ladder_config(rung), log_dir=log_dir)
        self.rung = rung

    def _finish(self, trace, chosen, candidates, calls, how):
        out = super()._finish(trace, chosen, candidates, calls, how)
        out['prompt_version'] = f"{out['prompt_version']}_{self.rung}"
        return out
