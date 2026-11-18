"""Day 4: action-budget-matched guided/random testing with browser-network synchronization.

Run from the WebStateCheck project root:
    python -m webstatecheck.day4_portable --repeats 3 --seeds 20261118 20261119 20261120

Evidence remains SYNTHETIC. This module deliberately does not use window.__research.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .day3_baseline import check_ui, make_guided_scenarios
from .server import create_server

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ("old", "new", "hello", "alpha", "beta", "fail")


def make_action_matched_random_scenarios(repeats: int, seed: int) -> list[dict[str, Any]]:
    """Match the guided suite's number of scenarios and query actions per trial.

    Random values and ordering are selected without targeting any seeded bug family.
    """
    if not 1 <= repeats <= 100:
        raise ValueError("repeats must be between 1 and 100")
    rng = random.Random(seed ^ 0x51C1A1)
    guided = make_guided_scenarios(repeats, seed)
    by_trial: dict[int, list[int]] = {}
    for item in guided:
        by_trial.setdefault(item["trial"], []).append(len(item["queries"]))
    results: list[dict[str, Any]] = []
    for trial, lengths in sorted(by_trial.items()):
        rng.shuffle(lengths)
        for length in lengths:
            results.append({"trial": trial, "queries": [rng.choice(QUERIES) for _ in range(length)]})
    return results


def scenario_budget(scenarios: list[dict[str, Any]]) -> dict[str, int]:
    return {"scenarios": len(scenarios), "query_actions": sum(len(r["queries"]) for r in scenarios)}


def _is_search_request(request: Any) -> bool:
    """Match fetch requests by URL/path, not instrumented page globals."""
    from urllib.parse import urlparse
    return urlparse(request.url).path == "/api/search"


def wait_for_search_requests(page: Any, queries: list[str], timeout_ms: int = 10000) -> dict[str, Any]:
    """Observe HTTP *responses*, not only fully downloaded response bodies.

    page.on("response") is delivered after the status/headers arrive. A page
    may process a non-2xx response without consuming its body; relying only
    on requestfinished left our HTTP 503 scenarios stuck as INCONCLUSIVE.

    HTTP 4xx/5xx are application-level responses, NOT transport failures.
    Use a separate UI oracle after the response(s) have been observed.
    This remains a research prototype and not a universal page-idle oracle.
    """
    if not queries:
        raise ValueError("at least one query is required")

    http_responses: list[dict[str, Any]] = []
    finished: list[str] = []
    failed: list[str] = []

    # Keep request object identities to avoid double counting a response that
    # is subsequently followed by a transport failure.
    received_ids: set[int] = set()
    failed_ids: set[int] = set()

    def on_response(response: Any) -> None:
        request = response.request
        if _is_search_request(request):
            received_ids.add(id(request))
            http_responses.append({"url": response.url, "status": response.status})

    def on_requestfinished(request: Any) -> None:
        if _is_search_request(request):
            finished.append(request.url)

    def on_requestfailed(request: Any) -> None:
        if _is_search_request(request):
            failed_ids.add(id(request))
            failed.append(request.url)

    # Register all listeners *before* initiating any network activity.
    page.on("response", on_response)
    page.on("requestfinished", on_requestfinished)
    page.on("requestfailed", on_requestfailed)

    for query in queries:
        page.locator("#query").fill(query)
        page.locator("#search").click()

    end = time.monotonic() + timeout_ms / 1000
    while len(received_ids | failed_ids) < len(queries) and time.monotonic() < end:
        page.wait_for_timeout(20)

    # Let the fetch() promise callbacks update the DOM. This is still a
    # fixture-specific settling heuristic; document that limitation.
    page.wait_for_timeout(150)
    return {
        "http_response_count": len(http_responses),
        "http_error_count": sum(item["status"] >= 400 for item in http_responses),
        "http_statuses": [item["status"] for item in http_responses],
        "requestfinished_count": len(finished),
        "requestfailed_count": len(failed),
        "timed_out": len(received_ids | failed_ids) < len(queries),
    }


def _launch_browser(playwright: Any) -> Any:
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium")
    if executable:
        return playwright.chromium.launch(headless=True, executable_path=executable)
    # Full Chromium already installed on user's Mac; avoid headless-shell download.
    return playwright.chromium.launch(headless=True, channel="chromium")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for strategy in ("guided", "random"):
        buggy = [r for r in rows if r["strategy"] == strategy and r["mode"] == "buggy"]
        fixed = [r for r in rows if r["strategy"] == strategy and r["mode"] == "fixed"]
        valid_buggy = [r for r in buggy if not r["inconclusive"]]
        valid_fixed = [r for r in fixed if not r["inconclusive"]]
        issues = sorted({issue for r in valid_buggy for issue in r["issues"]})
        times = [r["elapsed_ms"] for r in buggy + fixed]
        groups[strategy] = {
            "attempted_scenarios_per_version": len(buggy),
            "query_actions_per_version": sum(len(r["queries"]) for r in buggy),
            "inconclusive_checks": sum(r["inconclusive"] for r in buggy + fixed),
            "buggy_valid_checks": len(valid_buggy),
            "fixed_valid_checks": len(valid_fixed),
            "buggy_violations": sum(r["observed_violation"] for r in valid_buggy),
            "fixed_violations": sum(r["observed_violation"] for r in valid_fixed),
            "observed_issue_types": issues,
            "mean_elapsed_ms_per_check": round(mean(times), 1) if times else None,
        }
    return groups


def run(repeats: int, seeds: list[int]) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright
    if not 1 <= repeats <= 100:
        raise ValueError("repeats must be between 1 and 100")
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("provide at least one distinct seed")

    tasks: list[dict[str, Any]] = []
    for seed in seeds:
        guided = make_guided_scenarios(repeats, seed)
        random_scenarios = make_action_matched_random_scenarios(repeats, seed)
        assert scenario_budget(guided) == scenario_budget(random_scenarios)
        for strategy, scenarios in (("guided", guided), ("random", random_scenarios)):
            for item in scenarios:
                for mode in ("buggy", "fixed"):
                    tasks.append({"seed": seed, "strategy": strategy, "mode": mode,
                                  "trial": item["trial"], "queries": item["queries"]})
    random.Random(sum(seeds) ^ 0xCAFE).shuffle(tasks)

    httpd = create_server(port=0)
    port = httpd.server_address[1]
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    rows: list[dict[str, Any]] = []
    try:
        with sync_playwright() as playwright:
            browser = _launch_browser(playwright)
            try:
                for i, task in enumerate(tasks, 1):
                    context = browser.new_context(service_workers="block")
                    start = time.monotonic()
                    try:
                        page = context.new_page()
                        page.goto(f"http://127.0.0.1:{port}/?mode={task['mode']}")
                        completion = wait_for_search_requests(page, task["queries"])
                        state = {
                            "results": page.locator("#results").inner_text(),
                            "loading": page.locator("#status").inner_text(),
                            "error": page.locator("#error").inner_text(),
                        }
                        inconclusive = completion["timed_out"] or completion["requestfailed_count"] > 0
                        violation, issues = (False, []) if inconclusive else check_ui(task["queries"], state)
                        row = {
                            **task, "completion": completion, "ui_state": state,
                            "inconclusive": inconclusive, "observed_violation": violation,
                            "issues": issues,
                            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
                        }
                        rows.append(row)
                        label = "INCONCLUSIVE" if inconclusive else ("VIOLATION" if violation else "CLEAR")
                        print(f"[{label}] {i}/{len(tasks)} {task['strategy']} "
                              f"{task['mode']} {task['queries']}")
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=3)

    summary = summarize(rows)
    payload = {
        "project": "WebStateCheck Day 4 — Action-matched and hook-free synthetic comparison",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "evidence": "SYNTHETIC: same local fixture, hand-guided cases, application-specific oracle; NO AI",
        "repeats_per_seed": repeats, "seeds": seeds,
        "summary": summary, "observations": rows,
    }
    output = ROOT / "results"
    output.mkdir(parents=True, exist_ok=True)
    (output / "day4_observations.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md = [
        "# Day 4 — Equal-action-budget comparison (synthetic-only)", "",
        "**Scope:** The same intentionally buggy/fixed local fixture. No AI, no real-world validation.", "",
        f"Seeds: `{', '.join(map(str, seeds))}`; repetitions per seed: `{repeats}`.", "",
        "Browser synchronization: Playwright HTTP `response` / `requestfailed` events; **no** `window.__research` hook.", "",
        "| Strategy | Scenarios/version | Query actions/version | Buggy violations | Fixed violations | Inconclusive checks | Issue types | Mean ms/check |",
        "|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for name in ("guided", "random"):
        item = summary[name]
        md.append(
            f"| {name} | {item['attempted_scenarios_per_version']} | {item['query_actions_per_version']} | "
            f"{item['buggy_violations']} | {item['fixed_violations']} | {item['inconclusive_checks']} | "
            f"{', '.join(item['observed_issue_types']) or 'none'} | {item['mean_elapsed_ms_per_check']:.1f} |"
        )
    md += [
        "", "## Important qualifications", "",
        "- Guided tests intentionally target known fixture behaviors. Random tests do not.",
        "- Both strategies now receive the SAME scenario count and query-action budget per seed.",
        "- Only browser network events are used for synchronization, not a private JavaScript global.",
        "- HTTP `response` events count headers received, including 503; these do not prove the full body downloaded.",
        "- HTTP 503 is an HTTP response and counts as requestfinished, not requestfailed.",
        "- The UI oracle STILL depends on fixture-specific selectors and the expected result text.",
        "- The 150 ms after response headers is a pragmatic settling delay; other applications need better stabilization.",
        "- The repeated seeds are not independent applications. Do NOT call observed rates general accuracy.",
        "", "## Next", "",
        "1. Reproduce a documented public bug/fix pair with pinned commit versions.",
        "2. Replace fixture-specific selectors with a configurable per-application oracle.",
        "3. Add unguided/AI test selection with the same action and time budgets.",
        "4. Investigate timing sensitivity and uncertain/inconclusive cases.", "",
    ]
    (output / "day4_summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\nSaved: " + str(output / "day4_summary.md"))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seeds", nargs="+", type=int,
                        default=[20261118, 20261119, 20261120])
    args = parser.parse_args()
    run(args.repeats, args.seeds)


if __name__ == "__main__":
    main()
