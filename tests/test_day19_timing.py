"""Day 19 tests check data and logic only; real-source execution is on the user's Mac."""
import json
from pathlib import Path

import pytest

from webstatecheck.day19_timing import (
    SCHEMA, TARGET, TIMINGS, PROFILES, analyze, compare_day18, load_plans,
    render, run, validate_plan_object,
)


def valid_plan():
    return {'schema_version': SCHEMA, 'target_id': TARGET,
            'plans': [{'plan_id': 'gated-sync', 'first_task': 'gated', 'abort_timing': 'in_callback_sync'},
                      {'plan_id': 'gated-none', 'first_task': 'gated', 'abort_timing': 'none'}]}


def fake_records(n=2):
    p = valid_plan()['plans']
    output = []
    for repeat in range(1, n+1):
        for revision in ('before', 'after'):
            for plan in p:
                status = 'pending' if revision == 'before' or plan['abort_timing'] == 'none' else 'rejected'
                output.append({'repeat': repeat, 'revision': revision, 'plan_id': plan['plan_id'],
                               'first_task': plan['first_task'], 'abort_timing': plan['abort_timing'],
                               'first_status': status, 'next_started': status != 'pending',
                               'next_status': 'pending', 'first_error': None, 'signal_aborted': plan['abort_timing'] != 'none',
                               'queue_pending': 1, 'queue_size': 1, 'queue_error_events': [],
                               'task_submissions': 2, 'external_abort_mutations': 0, 'cleanup': 'finished'})
    return output


def test_valid_schema_and_accounting():
    out = validate_plan_object(valid_plan())
    assert out['scenarios'] == 2
    assert out['task_submissions_per_plan'] == 2
    assert out['external_abort_counts_as_extra_mutation'] is True
    assert set(TIMINGS) == {'in_callback_sync', 'in_callback_microtask', 'after_submit_external', 'none'}
    assert set(PROFILES) == {'gated', 'immediate'}


@pytest.mark.parametrize('field,value', [
    ('schema_version', 'v999'), ('target_id', 't02'), ('plans', []),
    ('plans', [{'plan_id': 'sync', 'first_task': 'gated', 'abort_timing': 'nonsense'}]),
    ('plans', [{'plan_id': 'sync', 'first_task': 'alien', 'abort_timing': 'none'}]),
])
def test_invalid_values_rejected(field, value):
    obj = valid_plan()
    obj[field] = value
    with pytest.raises(ValueError):
        validate_plan_object(obj)


def test_duplicate_and_unsafe_ids_rejected():
    obj = valid_plan()
    obj['plans'][1]['plan_id'] = obj['plans'][0]['plan_id']
    with pytest.raises(ValueError, match='duplicate'):
        validate_plan_object(obj)
    obj['plans'][1]['plan_id'] = '../secret'
    with pytest.raises(ValueError, match='Invalid'):
        validate_plan_object(obj)


def test_extra_fields_rejected():
    obj = valid_plan()
    obj['private_truth'] = 'not-allowed'
    with pytest.raises(ValueError):
        validate_plan_object(obj)
    obj = valid_plan()
    obj['plans'][0]['revision'] = 'before'
    with pytest.raises(ValueError):
        validate_plan_object(obj)


def test_catches_incomplete_and_duplicate_grid():
    rows = fake_records()
    with pytest.raises(ValueError, match='Incomplete'):
        analyze(rows[:-1], valid_plan()['plans'], 2)
    with pytest.raises(ValueError, match='Duplicate'):
        analyze(rows + [rows[0]], valid_plan()['plans'], 2)


def test_paired_changes_do_not_become_automatic_bugs():
    rows = fake_records()
    a = analyze(rows, valid_plan()['plans'], 2)
    assert a['total_executions'] == 8
    assert a['unique_changed_plans'] == ['gated-sync']
    assert len(a['paired_differences']) == 2
    assert a['repeat_instability'] == []


def test_repeat_instability_detected():
    rows = fake_records()
    rows[4]['queue_size'] = 2
    assert analyze(rows, valid_plan()['plans'], 2)['repeat_instability']


def test_crosscheck_day18_only_comparable_gated_records(tmp_path):
    prior = {'observe_ms': 50, 'records': []}
    rows = fake_records()
    mapping = {'gated-sync': 'sync_self_abort', 'gated-none': 'no_abort_control'}
    for row in rows:
        prior['records'].append({**row, 'case_id': mapping[row['plan_id']]})
    folder = tmp_path / 'results'
    folder.mkdir()
    (folder / 'day18_gap_observations.json').write_text(json.dumps(prior))
    result = compare_day18(tmp_path, rows, 50)
    assert result['compared'] == 8 and result['mismatches'] == []
    prior['records'][0]['next_started'] = not prior['records'][0]['next_started']
    (folder / 'day18_gap_observations.json').write_text(json.dumps(prior))
    assert len(compare_day18(tmp_path, rows, 50)['mismatches']) == 1
    assert compare_day18(tmp_path, rows, 100)['compared'] == 0


def test_summary_clearly_labels_development():
    rows = fake_records(1)
    report = {'records': rows, 'plans': valid_plan()['plans'], 'plan_stats': {'scenarios': 2},
              'plans_sha256': 'hash', 'runner_sha256': 'hash', 'repeats': 1,
              'analysis': analyze(rows, valid_plan()['plans'], 1),
              'day18_check': {'compared': 0, 'mismatches': []}}
    text = render(report)
    assert 'NOT A HELD-OUT AI BENCHMARK' in text
    assert 'NOT equalized' in text
    assert 'do not seal t01' in text


def test_no_invented_results_without_locked_project(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        run(tmp_path)


def test_bundled_plans_valid_and_cover_grid():
    root = Path(__file__).resolve().parent.parent
    plans, stats = load_plans(root)
    assert len(plans['plans']) == 8
    assert {(x['first_task'], x['abort_timing']) for x in plans['plans']} == {
        (profile, timing) for profile in PROFILES for timing in TIMINGS}
    assert stats['profiles'] == {'gated': 4, 'immediate': 4}
