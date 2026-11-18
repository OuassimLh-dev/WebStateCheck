from webstatecheck.day3_baseline import (
    check_ui, expected_for_seeded_fixture, infer_seeded_family,
    make_guided_scenarios, make_random_scenarios, summarize,
)


def test_random_reproducible_and_budget():
    x = make_random_scenarios(5, 77)
    assert x == make_random_scenarios(5, 77)
    assert len(x) == 20
    assert all(len(row['queries']) in (1, 2) for row in x)


def test_guided_budget():
    assert len(make_guided_scenarios(5, 77)) == 20


def test_seeded_labels_are_not_ui_oracle_inputs():
    assert infer_seeded_family(['old', 'hello']) == 'stale_response'
    assert infer_seeded_family(['new', 'old']) is None
    assert infer_seeded_family(['fail']) == 'stuck_loading'
    assert expected_for_seeded_fixture('buggy', ['fail'])
    assert not expected_for_seeded_fixture('fixed', ['fail'])


def test_ui_oracle_detects_state_errors():
    assert check_ui(['old', 'new'], {'results': 'Results for: old', 'loading': '', 'error': ''}) == (
        True, ['stale_or_incorrect_result'])
    assert check_ui(['fail'], {'results': 'No search yet.', 'loading': 'Loading...', 'error': 'fail'}) == (
        True, ['loading_not_cleared'])
    assert check_ui(['new'], {'results': 'Results for: new', 'loading': '', 'error': ''}) == (False, [])
    assert check_ui(['fail'], {'results': '', 'loading': '', 'error': 'Search failed'}) == (False, [])


def test_summary_keeps_strategies_separate():
    sample = [
        {'strategy': strategy, 'mode': mode, 'seeded_family': None,
         'observed_violation': False, 'as_expected': True, 'elapsed_ms': 10.0, 'queries': ['hello']}
        for strategy in ('guided', 'random') for mode in ('buggy', 'fixed')
    ]
    report = summarize(sample)
    assert report['guided']['total_checks'] == 2
    assert report['random']['total_checks'] == 2
    assert report['guided']['mean_elapsed_ms'] == 10
