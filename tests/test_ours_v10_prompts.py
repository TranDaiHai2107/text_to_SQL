"""Ours v10 prompt contract: no abstention, example-guided age/grain, explicit key joins."""
from ehrqa.agentic import prompts
from ehrqa.clinsql.proposed import PROPOSED_VERSION


def test_generate_and_repair_never_offer_null_sql():
    for stage in ('generate', 'repair'):
        text = prompts.system('clinsql', stage)
        assert 'or null' not in text.split('Return {', 1)[1].split('}', 1)[0]
        assert 'Do not force a query' not in text
    assert 'never null' in prompts.system('clinsql', 'generate')


def test_age_and_join_grain_follow_permitted_examples():
    text = prompts.system('clinsql', 'generate')
    assert 'follow its age expression' in text and 'p.anchor_age BETWEEN' in text
    assert 'Prefer EXISTS' not in text and 'explicit JOINs on the shared key' in text
    assert 'rather than anchor age alone' not in prompts.system('clinsql', 'link')


def test_versions_and_single_profile():
    assert prompts.VERSION.endswith('_v10') and PROPOSED_VERSION == 'clinsql_ours_v10'
    try:
        prompts.system('postgres', 'generate')
    except ValueError:
        pass
    else:
        raise AssertionError('PostgreSQL profile was removed')
