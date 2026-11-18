"""Regression tests for the missed unexpected_error case from Day 6."""
from webstatecheck.day6_oracles import DEFAULT_RULES, browser_facts, evaluate_rules, load_json

RULES = load_json(DEFAULT_RULES)["rules"]


def make_row(*, error: str, loading: str = "", result: str = "Results for: alpha") -> dict:
    return {
        "queries": ["fail", "alpha"],
        "completion": {"timed_out": False, "requestfailed_count": 0, "http_statuses": [503, 200]},
        "ui_state": {"results": result, "loading": loading, "error": error},
    }


def test_stale_error_after_success_is_violation():
    row = make_row(error="Search failed: HTTP 503")
    report = evaluate_rules("browser", browser_facts(row), RULES)
    assert report["verdict"] == "violation"
    assert any(r["rule"] == "successful_latest_query_must_clear_prior_error"
               and r["status"] == "violation" for r in report["rules"])


def test_cleared_error_after_success_is_clear():
    row = make_row(error="")
    assert evaluate_rules("browser", browser_facts(row), RULES)["verdict"] == "clear"


def test_stale_results_and_prior_error_are_detected():
    row = make_row(error="Search failed: HTTP 503", result="Results for: old")
    assert evaluate_rules("browser", browser_facts(row), RULES)["verdict"] == "violation"
