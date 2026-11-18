import json
from pathlib import Path

import pytest

from webstatecheck.day14_feasibility import analyze_sequence, audit, check_plan
from webstatecheck.day12_holdout import canonical_json
from webstatecheck.day13_target import TARGET, prepare
from tests.test_day13_target import fake_root


def a(typ, name):
    return {"type": typ, "target": name}


def test_reject_cancel_without_signal():
    result = analyze_sequence([a('cancel','current_signal'), a('click','observe_idle_status')])
    assert not result['executable_by_preconditions']
    assert 'does not exist' in result['errors'][0]


def test_reject_release_without_delayed_task():
    result = analyze_sequence([a('submit','enqueue_quick_task'), a('click','release_delayed_task')])
    assert not result['executable_by_preconditions']


def test_allow_submit_then_cancel():
    result = analyze_sequence([a('submit','enqueue_cancelable_task'), a('cancel','current_signal')])
    assert result['executable_by_preconditions']
    assert 'cancellation_sequence' in result['patterns']


def test_allow_delayed_then_release():
    result = analyze_sequence([a('submit','enqueue_delayed_task'), a('click','release_delayed_task')])
    assert result['executable_by_preconditions']
    assert not any('unreleased delayed' in s for s in result['warnings'])


def test_flag_stalled_task_without_release():
    result = analyze_sequence([a('submit','enqueue_delayed_task'), a('submit','enqueue_quick_task')])
    assert result['executable_by_preconditions']
    assert any('unreleased delayed' in s for s in result['warnings'])


def test_audit_reads_public_and_does_not_seal(tmp_path):
    root = fake_root(tmp_path)
    prepare(root)
    result = audit(root)
    assert result['enumerated_sequences'] == 49
    assert 0 < result['precondition_feasible_sequences'] < 49
    assert result['sequences_with_invalid_preconditions'] > 0
    assert (root / 'results/day14_feasibility.md').is_file()
    assert not (root / 'research/holdout_sealed/t01').exists()
    assert not (root / 'realworld').exists()
    assert 'issue_url' not in (root / 'results/day14_feasibility.md').read_text()


def test_check_plan_reports_impossible_trace(tmp_path):
    root = fake_root(tmp_path)
    prepare(root)
    plan = {"target_id": TARGET, "plans": [{"plan_id": "bad", "actions": [
        a('cancel','current_signal'), a('submit','enqueue_quick_task')]}]}
    p = tmp_path / 'candidate.json'
    p.write_text(canonical_json(plan))
    out = check_plan(p, root)
    assert out['scenarios'] == 1 and out['precondition_valid'] == 0


def test_check_plan_rejects_unregistered_action(tmp_path):
    root = fake_root(tmp_path)
    prepare(root)
    p = tmp_path / 'candidate.json'
    p.write_text(canonical_json({"target_id": TARGET, "plans": [{"plan_id": "bad", "actions": [
        a('submit','enqueue_quick_task'), a('click','teleport')]}]}))
    with pytest.raises(ValueError, match='outside public grammar'):
        check_plan(p, root)
