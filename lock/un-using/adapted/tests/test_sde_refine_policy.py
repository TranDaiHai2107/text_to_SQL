"""SDE result-shape rule parity against the locked native function."""
from ehrqa.clinsql.baselines.sde_refine_policy import native_refinement_reason
from ehrqa.clinsql.source_templates import isolated_function


def test_native_refine_decision_parity_on_synthetic_shapes():
    source = isolated_function('sde_sql_official', 'src/refine_new.py', 'is_need_refine')
    cases = [None, (), ((None,),), ((None,), (None,)),
             ((None,), (1,)), ((1,), (2,))]
    for rows in cases:
        native = {'data': None if rows is None else [tuple(row) for row in rows],
                  'sqlite_error': ''}
        expected = source(native, 0, 3)
        reason = native_refinement_reason(rows, try_times=0, max_try_times=3)
        assert bool(reason) == expected
    assert native_refinement_reason((), try_times=3, max_try_times=3) is None
