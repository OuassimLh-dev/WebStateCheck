"""Pure Python tests for Day 15: no network, npm, or actual Git clone required."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from webstatecheck.day15_executor import (
    action_options, smoke_scenarios, possible_scenarios, public_spec,
    verify_prepared_source, evaluate, REVISIONS,
)
from webstatecheck.day14_feasibility import analyze_sequence


def test_source_revisions_are_two_distinct_full_hashes():
    assert set(REVISIONS) == {"before", "after"}
    assert all(len(sha) == 40 for sha in REVISIONS.values())
    assert REVISIONS["before"] != REVISIONS["after"]


def test_smoke_all_pass_preconditions(monkeypatch):
    allowed = [{"type": kind, "target": target} for kind, target in [
        ("submit", "enqueue_quick_task"), ("submit", "enqueue_delayed_task"),
        ("submit", "enqueue_rejecting_task"), ("submit", "enqueue_cancelable_task"),
        ("cancel", "current_signal"), ("click", "release_delayed_task"),
        ("click", "observe_idle_status")]]
    monkeypatch.setattr("webstatecheck.day15_executor.action_options", lambda root=None: allowed)
    samples = smoke_scenarios(Path('.'))
    assert len(samples) == 6
    assert all(len(s["actions"]) == 2 for s in samples)
    assert all(analyze_sequence(s["actions"])["executable_by_preconditions"] for s in samples)


def test_plan_ids_unique(monkeypatch):
    allowed = [{"type":"submit", "target":"enqueue_quick_task"},
               {"type":"click", "target":"observe_idle_status"}]
    monkeypatch.setattr("webstatecheck.day15_executor.action_options", lambda root=None: allowed)
    monkeypatch.setattr("webstatecheck.day15_executor.public_spec", lambda root=None: {"actions_per_scenario": 2})
    rows = possible_scenarios(Path('.'))
    assert len({row["plan_id"] for row in rows}) == len(rows)
    assert len(rows) == 4


def test_untrusted_spec_never_replaces_day11_lock(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        public_spec(tmp_path)


def test_no_experiment_without_source(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        verify_prepared_source(tmp_path)


def test_no_verdict_if_experiment_not_prepared(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        evaluate("smoke", tmp_path)
