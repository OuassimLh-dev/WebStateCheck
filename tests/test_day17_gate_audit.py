"""Day 17 tests exercise analysis logic without GitHub or source builds."""
import pytest

from webstatecheck.day14_feasibility import analyze_sequence
from webstatecheck.day17_gate_audit import (
    precise_preconditions, public_three_action_plans, compare_pair,
    validate_executed_row, audit, matrix,
)

Q = {"type": "submit", "target": "enqueue_quick_task"}
D = {"type": "submit", "target": "enqueue_delayed_task"}
R = {"type": "click", "target": "release_delayed_task"}
C = {"type": "submit", "target": "enqueue_cancelable_task"}
X = {"type": "cancel", "target": "current_signal"}
O = {"type": "click", "target": "observe_idle_status"}
E = {"type": "submit", "target": "enqueue_rejecting_task"}
OPTIONS = [Q, D, E, C, X, R, O]


def record(actions, status, unreleased=0, outcomes=None):
    return {"plan_id": "p1", "actions": actions, "status": status,
            "unreleased_gates": unreleased,
            "pending_task_records": 0,
            "queue_snapshot": {"pending": 0, "size": 0, "observed_idle": None},
            "max_active": 1, "outcomes": outcomes if outcomes is not None else [], "events": []}


def test_tracks_unreleased_multiplicity_not_a_boolean():
    actions = [D, D, R]
    assert precise_preconditions(actions)["unreleased_gates_predicted"] == 1
    assert precise_preconditions(actions)["post_action_state"] == "needs_release"
    assert not any("unreleased delayed" in w for w in analyze_sequence(actions)["warnings"])


def test_balances_release_and_reenqueues():
    assert precise_preconditions([D, R, D])["unreleased_gates_predicted"] == 1
    assert precise_preconditions([D, R, Q])["unreleased_gates_predicted"] == 0
    assert precise_preconditions([D, R, R])["executable_by_preconditions"] is False


def test_two_gates_without_release():
    result = precise_preconditions([D, D, Q])
    assert result["unreleased_gates_predicted"] == 2
    assert result["task_submissions"] == 3


def test_cancel_requires_signal_and_repeat_is_warning():
    assert not precise_preconditions([X, Q, O])["executable_by_preconditions"]
    once = precise_preconditions([C, X, O])
    assert once["executable_by_preconditions"] and "cancellation_action" in once["patterns"]
    twice = precise_preconditions([C, X, X])
    assert twice["executable_by_preconditions"] and any("already cancelled" in w for w in twice["warnings"])


def test_observation_is_counted_as_action():
    row = precise_preconditions([Q, O, O])
    assert row["observation_actions"] == 2
    assert any("action slot" in w for w in row["warnings"])


def test_schema_is_exact_and_unsupported_rejected():
    bad = [{"type": "submit", "target": "enqueue_delayed_task", "hidden": "x"}, Q, O]
    assert not precise_preconditions(bad)["executable_by_preconditions"]
    assert not precise_preconditions([{"type": "unknown", "target": "x"}, Q, O])["executable_by_preconditions"]


def test_full_public_matrix_has_stable_ids_and_feasible_plans():
    valid, rows = public_three_action_plans(OPTIONS)
    assert len(rows) == 343
    assert len(valid) == 154
    assert len({p["plan_id"] for p in valid}) == 154
    assert all(len(p["actions"]) == 3 for p in valid)
    assert all(precise_preconditions(p["actions"])["executable_by_preconditions"] for p in valid)


def test_dynamic_bookkeeping_catches_bogus_settled_state():
    issues = validate_executed_row(record([D, D, R], "settled", unreleased=0))
    assert len(issues) >= 2
    good = validate_executed_row(record([D, D, R], "needs_release", unreleased=1))
    assert good == []


def test_zero_pending_gates_can_be_unresolved_without_false_alarm():
    assert validate_executed_row(record([Q, O, O], "unresolved", unreleased=0)) == []
    assert validate_executed_row(record([Q, O, O], "needs_release", unreleased=0))


def test_differential_comparison_includes_task_outcomes_not_only_status():
    a = record([Q, Q, O], "settled", outcomes=[{"id": 1, "type": "quick", "status": "fulfilled", "value": "ok"}])
    b = record([Q, Q, O], "settled", outcomes=[{"id": 1, "type": "quick", "status": "rejected", "error": "oops"}])
    assert compare_pair(a, b) == ["outcomes"]
    assert compare_pair(a, a) == []


def test_no_privately_selected_target_or_remote_requirement(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        audit(tmp_path)
    with pytest.raises((ValueError, FileNotFoundError)):
        matrix(tmp_path, repeats=1)
    with pytest.raises(ValueError, match="repeats"):
        matrix(tmp_path, repeats=0)


def test_exactly_one_boolean_gate_warning_missed_in_public_triples():
    plans, rows = public_three_action_plans(OPTIONS)
    old_rows = {r["plan_id"]: r for r in __import__(
        "webstatecheck.day16_three_action", fromlist=["enumerate_sequences"]
    ).enumerate_sequences(OPTIONS)}
    missed = [r["plan_id"] for r in rows
              if r["executable_by_preconditions"]
              and r["unreleased_gates_predicted"] > 0
              and not any("unreleased delayed" in w for w in old_rows[r["plan_id"]]["warnings"])]
    assert len(missed) == 1


def test_audit_checks_previous_smoke_records_without_modifying_protocol(tmp_path, monkeypatch):
    import json
    import webstatecheck.day17_gate_audit as day17
    monkeypatch.setattr(day17, "public_spec", lambda root: {
        "actions_per_scenario": 2, "scenarios_per_method": 4,
    })
    monkeypatch.setattr(day17, "action_options", lambda root: OPTIONS)
    outdir = tmp_path / "results"
    outdir.mkdir()
    sample = record([D, D, R], "needs_release", unreleased=1)
    (outdir / "day16_smoke_observations.json").write_text(json.dumps({
        "records": [{"revision": "before", **sample}, {"revision": "after", **sample}]
    }))
    result = day17.audit(tmp_path)
    assert result["smoke_records_checked"] == 2
    assert result["smoke_bookkeeping_issues"] == []
    assert len(result["old_checker_missed_unreleased_gate_warnings"]) == 1
    assert (outdir / "day17_gate_audit.md").is_file()
