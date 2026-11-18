from webstatecheck.exploration import (
    KINDS, evaluate_ui, expected_violation, make_scenarios
)


def test_scenario_generation_reproducible_and_balanced():
    a = make_scenarios(10, 42)
    b = make_scenarios(10, 42)
    assert a == b
    assert len(a) == 40
    for trial in range(1, 11):
        subset = [s for s in a if s['trial'] == trial]
        assert {s['kind'] for s in subset} == set(KINDS)


def test_oracle_ignores_fixture_mode_and_catches_stale_result():
    violated, reasons = evaluate_ui(
        'overlap_stale', ['old', 'new'],
        {'results': 'Results for: old', 'loading': '', 'error': ''}
    )
    assert violated
    assert reasons == ['results_did_not_match_latest_query']


def test_oracle_catches_stuck_loading_after_failure():
    violated, reasons = evaluate_ui(
        'request_failure', ['fail'],
        {'results': '', 'loading': 'Loading...', 'error': 'Search failed: HTTP 503'}
    )
    assert violated
    assert reasons == ['loading_indicator_remained_visible']


def test_oracle_accepts_fixed_state_and_control():
    for kind, queries, state in [
        ('overlap_stale', ['old', 'new'], {'results': 'Results for: new', 'loading': '', 'error': ''}),
        ('overlap_control', ['new', 'old'], {'results': 'Results for: old', 'loading': '', 'error': ''}),
        ('request_failure', ['fail'], {'results': '', 'loading': '', 'error': 'Search failed: HTTP 503'}),
    ]:
        assert evaluate_ui(kind, queries, state) == (False, [])


def test_synthetic_ground_truth():
    for kind in KINDS:
        assert expected_violation('fixed', kind) is False
    assert expected_violation('buggy', 'request_failure')
    assert expected_violation('buggy', 'overlap_stale')
    assert not expected_violation('buggy', 'overlap_control')
    assert not expected_violation('buggy', 'single_success')
