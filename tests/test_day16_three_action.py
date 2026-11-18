"""Pure local Day 16 tests; never require GitHub or an upstream JS build."""
from pathlib import Path

import pytest

from webstatecheck.day14_feasibility import analyze_sequence
from webstatecheck.day16_three_action import (
    BUDGET_V2, SMOKE_TRIPLES, enumerate_sequences,
    smoke_scenarios, analyze, run_smoke,
)

OPTIONS = [
    {'type': 'submit', 'target': 'enqueue_quick_task'},
    {'type': 'submit', 'target': 'enqueue_delayed_task'},
    {'type': 'submit', 'target': 'enqueue_rejecting_task'},
    {'type': 'submit', 'target': 'enqueue_cancelable_task'},
    {'type': 'cancel', 'target': 'current_signal'},
    {'type': 'click', 'target': 'release_delayed_task'},
    {'type': 'click', 'target': 'observe_idle_status'},
]


def test_enumerates_all_343_sequences_with_unique_ids():
    rows = enumerate_sequences(OPTIONS)
    assert len(rows) == 7**3
    assert len(set(r['plan_id'] for r in rows)) == len(rows)
    assert all(len(r['actions']) == BUDGET_V2 for r in rows)
    assert any(not r['executable_by_preconditions'] for r in rows)
    assert any(r['executable_by_preconditions'] for r in rows)


def test_smoke_sequences_are_legal_three_action_plans():
    plans = smoke_scenarios(OPTIONS)
    assert len(plans) == len(SMOKE_TRIPLES) == 14
    assert len({p['plan_id'] for p in plans}) == len(plans)
    assert all(len(p['actions']) == 3 for p in plans)
    assert all(analyze_sequence(p['actions'])['executable_by_preconditions'] for p in plans)


def test_preconditions_reject_cancel_before_enqueuing():
    seq = [OPTIONS[4], OPTIONS[0], OPTIONS[6]]
    row = analyze_sequence(seq)
    assert not row['executable_by_preconditions']


def test_three_action_delayed_release_can_be_completed():
    seq = [OPTIONS[1], OPTIONS[0], OPTIONS[5]]
    row = analyze_sequence(seq)
    assert row['executable_by_preconditions']
    assert not any('unreleased delayed' in s for s in row['warnings'])


def test_three_action_pending_gate_is_not_treated_as_settled():
    seq = [OPTIONS[1], OPTIONS[0], OPTIONS[6]]
    row = analyze_sequence(seq)
    assert row['executable_by_preconditions']
    assert any('unreleased delayed' in s for s in row['warnings'])


def test_reject_duplicate_action_names():
    with pytest.raises(ValueError):
        enumerate_sequences([OPTIONS[0], OPTIONS[0]])


def test_refuses_to_run_with_missing_frozen_protocol(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        analyze(tmp_path)
    with pytest.raises((FileNotFoundError, ValueError)):
        run_smoke(tmp_path)
