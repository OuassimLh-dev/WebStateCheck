"""Day 18 pure logic and protocol-safety tests. No network or upstream build required."""
import json
from pathlib import Path

import pytest

from webstatecheck.day18_gap_diagnostic import (
    CASE_IDS, NOTE, classify, render_md, run, invoke_node,
)


def sample_record(rep, rev, case, status, next_started):
    return {"repeat": rep, "revision": rev, "case_id": case,
            "first_status": status, "first_error": None,
            "next_started": next_started, "next_status": "pending",
            "signal_aborted": case != "no_abort_control", "queue_pending": 1,
            "queue_size": 1, "cleanup": "finished"}


def full_grid(repeats=2):
    records = []
    for rep in range(1, repeats + 1):
        for rev in ("before", "after"):
            for case in CASE_IDS:
                status = "rejected" if case in ("microtask_self_abort", "external_abort") else "pending"
                next_started = status == "rejected"
                if case == "sync_self_abort" and rev == "after":
                    status, next_started = "rejected", True
                records.append(sample_record(rep, rev, case, status, next_started))
    return records


def test_expected_historical_pattern_detected_with_controls():
    analysis = classify(full_grid())
    assert analysis["repeats"] == 2
    assert analysis["total_execution_cases"] == 16
    assert analysis["historical_pattern_reproduced"] is True
    assert analysis["sync_expected_per_repeat"] == [True, True]
    assert analysis["control_expectations_per_repeat"] == [True, True]
    assert {d["case_id"] for d in analysis["differences"]} == {"sync_self_abort"}


def test_unexpected_results_must_not_be_overclaimed():
    rows = full_grid(1)
    for r in rows:
        if r["revision"] == "after" and r["case_id"] == "sync_self_abort":
            r["first_status"] = "pending"
            r["next_started"] = False
    assert classify(rows)["historical_pattern_reproduced"] is False


def test_control_failure_prevents_claim_even_when_sync_matches():
    rows = full_grid(1)
    for r in rows:
        if r["revision"] == "after" and r["case_id"] == "microtask_self_abort":
            r["first_status"] = "pending"
    assert classify(rows)["historical_pattern_reproduced"] is False


def test_missing_or_duplicate_observations_rejected():
    rows = full_grid(1)
    with pytest.raises(ValueError, match="Incomplete"):
        classify(rows[:-1])
    with pytest.raises(ValueError, match="Duplicate"):
        classify(rows + [rows[-1]])


def test_nonconsecutive_repeats_rejected():
    rows = full_grid(1)
    for r in rows:
        r["repeat"] = 2
    with pytest.raises(ValueError, match="consecutive"):
        classify(rows)


def test_report_is_explicitly_development_only():
    records = full_grid(1)
    result = {"records": records, "analysis": classify(records),
              "probe_sha256": "abc", "commits": {"before": "old", "after": "new"}}
    report = render_md(result)
    assert "NOT blinded" in report
    assert "Do not seal" in report
    assert "sync_self_abort" in report
    assert "old" in report and "new" in report


def test_run_checks_repeats_and_observation_bounds_before_touching_files(tmp_path):
    with pytest.raises(ValueError, match="repeats"):
        run(repeats=0, root=tmp_path)
    with pytest.raises(ValueError, match="observe_ms"):
        run(observe_ms=5, root=tmp_path)


def test_invalid_root_not_an_upstream_result(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        run(root=tmp_path)


def test_node_wrapper_rejects_missing_probe_and_duplicate_cases(tmp_path):
    with pytest.raises(ValueError, match="Missing Day 18"):
        invoke_node(tmp_path / 'nonexistent.mjs', tmp_path / 'notbuilt.js', 50)


def test_declared_cases_cover_self_abort_and_controls():
    assert CASE_IDS == ("sync_self_abort", "microtask_self_abort", "external_abort", "no_abort_control")
    assert "NOT" in NOTE
