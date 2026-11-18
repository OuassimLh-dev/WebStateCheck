"""Offline checks for Day 8 casebook. No external network or browser."""
import json
from pathlib import Path
import pytest

from webstatecheck.day8_casebook import process_observation, aggregate, get_rules, run


def test_browser_label_is_not_used_for_detection(tmp_path):
    rules = [{"id":"r","source":"browser","when":[{"field":"error_visible","op":"eq","value":True}],
              "require":[{"field":"loading_visible","op":"eq","value":False}]}]
    raw = {"queries":["fail"], "ui_state":{"error":"HTTP 503", "loading":"Loading...", "results":""},
           "completion":{"timed_out":False,"requestfailed_count":0,"http_statuses":[503]},"observed_violation":True}
    a = process_observation("browser",{**raw,"mode":"buggy"},rules,1)
    b = process_observation("browser",{**raw,"mode":"fixed"},rules,2)
    assert a["verdict"] == b["verdict"] == "violation"


def test_final_form_and_axios_labels_do_not_affect_verdict():
    rules = [
        {"id":"form","source":"final_form","when":[{"field":"newer_validation_pending","op":"eq","value":True}],
         "require":[{"field":"validating","op":"eq","value":True}]},
        {"id":"axios","source":"axios","when":[{"field":"cancellation_requested","op":"eq","value":True}],
         "require":[{"field":"all_listeners_notified","op":"eq","value":True}]},
    ]
    for label in ("before", "after"):
        form = process_observation("final_form",{"label":label,"after_older_resolved":{"validating":False},"violation":True},rules,1)
        axios = process_observation("axios",{"label":label,"scenario":"x","cancellation_requested":True,"all_listeners_notified":False,"unexpected_exception":False,"verdict":"violation"},rules,1)
        assert form["verdict"] == axios["verdict"] == "violation"


def test_aggregate_groups_by_source_and_revision():
    rows = [{"source":"axios","label_for_analysis_only":"before","verdict":"violation"},
            {"source":"axios","label_for_analysis_only":"before","verdict":"clear"},
            {"source":"axios","label_for_analysis_only":"after","verdict":"clear"}]
    got = aggregate(rows)
    assert got["axios:before"]["cases"] == 2
    assert got["axios:before"]["violation"] == 1
    assert got["axios:after"]["clear"] == 1


def test_run_requires_actual_evidence(tmp_path):
    (tmp_path / "research" / "oracles").mkdir(parents=True)
    for name in ("day6_rules.json", "day7_axios_rules.json"):
        (tmp_path / "research" / "oracles" / name).write_text('{"rules": [{"id":"x","source":"browser","when":[{"field":"error_visible","op":"eq","value":true}],"require":[{"field":"loading_visible","op":"eq","value":false}]}]}')
    with pytest.raises((ValueError, FileNotFoundError)):
        run(root=tmp_path)


def test_reanalysis_end_to_end_with_minimal_input(tmp_path):
    r = tmp_path / "research" / "oracles"
    r.mkdir(parents=True)
    (tmp_path / "results").mkdir()
    d6 = {"rules":[
        {"id":"browser-rule","source":"browser","when":[{"field":"error_visible","op":"eq","value":True}],"require":[{"field":"loading_visible","op":"eq","value":False}]},
        {"id":"final-rule","source":"final_form","when":[{"field":"newer_validation_pending","op":"eq","value":True}],"require":[{"field":"validating","op":"eq","value":True}]},
    ]}
    d7 = {"rules":[{"id":"axios-rule","source":"axios","when":[{"field":"cancellation_requested","op":"eq","value":True}],"require":[{"field":"all_listeners_notified","op":"eq","value":True}]}]}
    (r / "day6_rules.json").write_text(json.dumps(d6))
    (r / "day7_axios_rules.json").write_text(json.dumps(d7))
    payloads = {
       "day4_observations.json": {"observations":[{"mode":"buggy","queries":["fail"],"completion":{"timed_out":False,"requestfailed_count":0},"ui_state":{"error":"error", "loading":"Loading..."},"observed_violation":True}]},
       "day5_realworld.json": {"observations":[{"label":"before","after_older_resolved":{"validating":False},"violation":True}]},
       "day7_axios_observations.json": {"observations":[{"label":"before","cancellation_requested":True,"all_listeners_notified":False,"unexpected_exception":True,"verdict":"violation"}]},
    }
    for name,obj in payloads.items():
        (tmp_path / "results" / name).write_text(json.dumps(obj))
    result = run(root=tmp_path)
    assert result["cases"] == 3
    assert result["totals"]["violation"] == 3
    assert result["disagreement_count"] == 0
    assert (tmp_path / "results" / "day8_casebook_summary.md").exists()
    assert (tmp_path / "results" / "day8_casebook.json").exists()


def test_never_infers_missing_facts_as_clear():
    rule = [{"id":"r","source":"axios","when":[{"field":"cancellation_requested","op":"eq","value":True}],
             "require":[{"field":"all_listeners_notified","op":"eq","value":True}]}]
    row = process_observation("axios",{"cancellation_requested":True,"all_listeners_notified":None},rule,1)
    assert row["verdict"] == "inconclusive"
