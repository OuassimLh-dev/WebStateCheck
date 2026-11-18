"""Only unit/integration tests using controlled tiny observations. No new browser experiments."""
import json
from pathlib import Path

import pytest

from webstatecheck.day6_oracles import (
    DEFAULT_RULES, browser_facts, check_condition, evaluate_rules,
    final_form_facts, load_json, run,
)

RULES = load_json(DEFAULT_RULES)["rules"]


def test_true_and_false_conditions_do_not_confuse_bool_with_int():
    assert check_condition({"flag": True}, {"field": "flag", "op": "eq", "value": True}) is True
    assert check_condition({"flag": 1}, {"field": "flag", "op": "eq", "value": True}) is False
    assert check_condition({}, {"field": "flag", "op": "eq", "value": True}) is None


def test_invalid_operator_rejected():
    with pytest.raises(ValueError):
        check_condition({"x": 1}, {"field": "x", "op": "execute", "value": 1})


def test_day5_bug_verdict_uses_only_state_not_revision_label():
    before = {"label": "fixed", "after_older_resolved": {"validating": False}}
    after = {"label": "buggy", "after_older_resolved": {"validating": True}}
    assert evaluate_rules("final_form", final_form_facts(before), RULES)["verdict"] == "violation"
    assert evaluate_rules("final_form", final_form_facts(after), RULES)["verdict"] == "clear"


def test_browser_error_loading_violation_and_clear():
    row = {"queries": ["fail"], "completion": {"timed_out": False, "requestfailed_count": 0},
           "ui_state": {"results": "No search yet.", "error": "HTTP 503", "loading": "Loading..."}}
    assert evaluate_rules("browser", browser_facts(row), RULES)["verdict"] == "violation"
    row["ui_state"]["loading"] = ""
    assert evaluate_rules("browser", browser_facts(row), RULES)["verdict"] == "clear"


def test_browser_stale_results_detected():
    row = {"queries": ["old", "new"], "completion": {"timed_out": False, "requestfailed_count": 0},
           "ui_state": {"results": "Results for: old", "error": "", "loading": ""}}
    assert evaluate_rules("browser", browser_facts(row), RULES)["verdict"] == "violation"


def test_missing_field_is_inconclusive_not_clean():
    row = {"queries": ["old", "new"], "completion": {}, "ui_state": {"error": "", "loading": ""}}
    assert evaluate_rules("browser", browser_facts(row), RULES)["verdict"] == "inconclusive"


def test_not_covered_is_distinct_from_clear():
    # Error is not visible and last query itself failed; no invariant is applicable.
    row = {"queries": ["fail"], "completion": {"timed_out": False},
           "ui_state": {"error": "", "loading": "", "results": "No search yet."}}
    assert evaluate_rules("browser", browser_facts(row), RULES)["verdict"] == "not_covered"


def test_run_generates_report_from_fake_saved_observations(tmp_path):
    a = tmp_path / "d4.json"
    b = tmp_path / "d5.json"
    a.write_text(json.dumps({"observations": [
        {"mode": "buggy", "observed_violation": True, "inconclusive": False,
         "queries": ["fail"], "completion": {"timed_out": False},
         "ui_state": {"error": "HTTP 503", "loading": "Loading...", "results": "No search yet."}},
        {"mode": "fixed", "observed_violation": False, "inconclusive": False,
         "queries": ["fail"], "completion": {"timed_out": False},
         "ui_state": {"error": "HTTP 503", "loading": "", "results": "No search yet."}},
    ]}))
    b.write_text(json.dumps({"observations": [
        {"label": "before", "violation": True, "after_older_resolved": {"validating": False}},
        {"label": "after", "violation": False, "after_older_resolved": {"validating": True}},
    ]}))
    data = run(a, b, DEFAULT_RULES, tmp_path / "results")
    assert data["counts"]["browser"] == {"violation": 1, "clear": 1}
    assert data["counts"]["final_form"] == {"violation": 1, "clear": 1}
    assert data["disagreement_count"] == 0
    assert (tmp_path / "results" / "day6_oracle_summary.md").exists()
