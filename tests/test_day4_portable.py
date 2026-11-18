from types import SimpleNamespace

import pytest

from webstatecheck.day3_baseline import make_guided_scenarios
from webstatecheck.day4_portable import (
    _is_search_request,
    make_action_matched_random_scenarios,
    scenario_budget,
    summarize,
    wait_for_search_requests,
)


def test_action_budget_is_equal_for_many_seeds():
    for seed in (1, 10, 20261118, 20261119, 20261120):
        for repeats in (1, 3, 5):
            guided = make_guided_scenarios(repeats, seed)
            random_cases = make_action_matched_random_scenarios(repeats, seed)
            assert scenario_budget(guided) == scenario_budget(random_cases)
            assert scenario_budget(guided) == {"scenarios": 4 * repeats, "query_actions": 6 * repeats}


def test_random_reproducible_with_different_seeds():
    a = make_action_matched_random_scenarios(5, 77)
    assert a == make_action_matched_random_scenarios(5, 77)
    assert a != make_action_matched_random_scenarios(5, 78)


def test_invalid_repeats_rejected():
    for bad in (0, 101):
        with pytest.raises(ValueError):
            make_action_matched_random_scenarios(bad, 7)


def test_search_request_matcher_ignores_unrelated_requests():
    assert _is_search_request(SimpleNamespace(url="http://localhost/api/search?q=old"))
    assert not _is_search_request(SimpleNamespace(url="http://localhost/app.js"))
    assert not _is_search_request(SimpleNamespace(url="http://localhost/api/search-other"))


class _FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def fill(self, query):
        self.page.current_query = query

    def click(self):
        self.page.pending.append(self.page.current_query)


class _FakeRequest:
    def __init__(self, query):
        self.url = "http://127.0.0.1:9876/api/search?q=" + query


class _FakeResponse:
    def __init__(self, request, status):
        self.request = request
        self.url = request.url
        self.status = status


class _FakePage:
    def __init__(self, emit_finished=True, transport_fail=False):
        self.callbacks = {}
        self.current_query = None
        self.pending = []
        self.emit_finished = emit_finished
        self.transport_fail = transport_fail

    def on(self, event_name, callback):
        self.callbacks[event_name] = callback

    def locator(self, selector):
        return _FakeLocator(self, selector)

    def wait_for_timeout(self, ms):
        if self.pending:
            query = self.pending.pop(0)
            request = _FakeRequest(query)
            if self.transport_fail:
                self.callbacks["requestfailed"](request)
            else:
                status = 503 if query == "fail" else 200
                self.callbacks["response"](_FakeResponse(request, status))
                if self.emit_finished:
                    self.callbacks["requestfinished"](request)


def test_network_responses_replace_private_app_hook():
    page = _FakePage()
    result = wait_for_search_requests(page, ["old", "new"], timeout_ms=1000)
    assert result == {
        "http_response_count": 2, "http_error_count": 0,
        "http_statuses": [200, 200],
        "requestfinished_count": 2, "requestfailed_count": 0,
        "timed_out": False,
    }
    assert page.pending == []


def test_http_503_does_not_timeout_even_without_requestfinished():
    page = _FakePage(emit_finished=False)
    result = wait_for_search_requests(page, ["fail"], timeout_ms=1000)
    assert result["http_response_count"] == 1
    assert result["http_error_count"] == 1
    assert result["http_statuses"] == [503]
    assert result["requestfinished_count"] == 0
    assert result["requestfailed_count"] == 0
    assert result["timed_out"] is False


def test_true_transport_failure_is_recorded_separately():
    page = _FakePage(transport_fail=True)
    result = wait_for_search_requests(page, ["fail"], timeout_ms=1000)
    assert result["http_response_count"] == 0
    assert result["requestfailed_count"] == 1
    assert result["timed_out"] is False


def test_duplicate_queries_count_as_two_requests():
    page = _FakePage(emit_finished=False)
    result = wait_for_search_requests(page, ["alpha", "alpha"], timeout_ms=1000)
    assert result["http_response_count"] == 2
    assert result["timed_out"] is False


def test_summary_distinguishes_inconclusive():
    rows = []
    for strategy in ("guided", "random"):
        for mode in ("buggy", "fixed"):
            rows.append({
                "strategy": strategy, "mode": mode,
                "queries": ["hello"], "inconclusive": False,
                "observed_violation": mode == "buggy", "issues": ["sample"] if mode == "buggy" else [],
                "elapsed_ms": 50.0,
            })
    data = summarize(rows)
    assert data["guided"]["buggy_violations"] == 1
    assert data["random"]["query_actions_per_version"] == 1
    rows[0]["inconclusive"] = True
    data = summarize(rows)
    assert data["guided"]["buggy_violations"] == 0
    assert data["guided"]["inconclusive_checks"] == 1
