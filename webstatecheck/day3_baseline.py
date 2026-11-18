"""Day 3: compare guided vs. unguided scenario selection on ONE synthetic fixture.

This is an engineering baseline, NOT a novel bug detector, general detection
accuracy, or a real-world benchmark. Usage:
    python -m webstatecheck.day3_baseline --repeats 5 --seed 20261118
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

from .exploration import make_scenarios
from .server import create_server

ROOT = Path(__file__).resolve().parent.parent
FAST = ("new", "hello", "alpha", "beta")
SUCCESSFUL = ("old",) + FAST
SINGLE = SUCCESSFUL + ("fail",)


def make_random_scenarios(repeats: int, seed: int) -> list[dict[str, Any]]:
    """Use a fixed request budget: 4 scenarios per repeat, no bug-category targeting."""
    if not 1 <= repeats <= 100:
        raise ValueError("repeats must be 1..100")
    rng = random.Random(seed)
    scenarios = []
    for trial in range(1, repeats + 1):
        for _ in range(4):
            if rng.random() < 0.5:
                queries = [rng.choice(SINGLE)]
            else:
                queries = [rng.choice(SUCCESSFUL), rng.choice(SUCCESSFUL)]
            scenarios.append({"trial": trial, "queries": queries})
    return scenarios


def make_guided_scenarios(repeats: int, seed: int) -> list[dict[str, Any]]:
    """Guided scenarios from Day 2; discard family labels before the oracle."""
    return [{"trial": case["trial"], "queries": case["queries"]}
            for case in make_scenarios(repeats, seed)]


def infer_seeded_family(queries: list[str]) -> str | None:
    """Known fixture's reference labeling; never given to the UI oracle.

    This label does NOT generalize to arbitrary applications.
    """
    if len(queries) == 1 and queries[0] == "fail":
        return "stuck_loading"
    if len(queries) == 2 and queries[0] == "old" and queries[1] in FAST:
        return "stale_response"
    return None


def check_ui(queries: list[str], state: dict[str, str]) -> tuple[bool, list[str]]:
    """Check app-visible UI against query intent; never consult bug/fix mode.

    This remains an application-specific UI oracle, not a universal oracle.
    """
    if not queries or len(queries) > 2:
        raise ValueError("one or two queries expected")
    issues = []
    if state["loading"].strip():
        issues.append("loading_not_cleared")
    if queries[-1] == "fail":
        if not state["error"].strip():
            issues.append("failure_not_displayed")
    else:
        if state["error"].strip():
            issues.append("unexpected_error")
        if state["results"].strip() != f"Results for: {queries[-1]}":
            issues.append("stale_or_incorrect_result")
    return bool(issues), issues


def expected_for_seeded_fixture(mode: str, queries: list[str]) -> bool:
    return mode == "buggy" and infer_seeded_family(queries) is not None


def _browser(playwright):
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium")
    if executable:
        return playwright.chromium.launch(headless=True, executable_path=executable)
    # Full Chromium (previously installed) avoids requiring Headless Shell.
    return playwright.chromium.launch(headless=True, channel="chromium")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for strategy in ("guided", "random"):
        subset = [row for row in rows if row["strategy"] == strategy]
        buggy = [row for row in subset if row["mode"] == "buggy"]
        fixed = [row for row in subset if row["mode"] == "fixed"]
        groups[strategy] = {
            "scenario_pairs": len(buggy),
            "query_actions_per_version": sum(len(r["queries"]) for r in buggy),
            "known_bug_families_exercised": sorted({r["seeded_family"] for r in buggy if r["seeded_family"]}),
            "buggy_violations": sum(r["observed_violation"] for r in buggy),
            "fixed_violations": sum(r["observed_violation"] for r in fixed),
            "matches_seeded_expectations": sum(r["as_expected"] for r in subset),
            "total_checks": len(subset),
            "mean_elapsed_ms": round(mean(r["elapsed_ms"] for r in subset), 1) if subset else None,
        }
    return groups


def run(repeats: int, seed: int) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    scenarios = {
        "guided": make_guided_scenarios(repeats, seed),
        "random": make_random_scenarios(repeats, seed),
    }
    tasks = []
    for strategy, cases in scenarios.items():
        for case in cases:
            for mode in ("buggy", "fixed"):
                tasks.append({"strategy": strategy, "mode": mode, **case})
    random.Random(seed + 1).shuffle(tasks)

    server = create_server(port=0)
    port = server.server_address[1]
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    rows = []
    try:
        with sync_playwright() as playwright:
            browser = _browser(playwright)
            try:
                for number, task in enumerate(tasks, 1):
                    context = browser.new_context(service_workers="block")
                    start = time.monotonic()
                    try:
                        page = context.new_page()
                        page.goto(f"http://127.0.0.1:{port}/?mode={task['mode']}")
                        for query in task["queries"]:
                            page.locator("#query").fill(query)
                            page.locator("#search").click()
                        # Internal completion counter synchronizes our controlled fixture.
                        # A general-purpose tool cannot assume this hook exists.
                        page.wait_for_function(
                            "n => window.__research.completed.length === n",
                            arg=len(task["queries"]), timeout=10000,
                        )
                        page.wait_for_timeout(30)
                        state = {
                            "results": page.locator("#results").inner_text(),
                            "loading": page.locator("#status").inner_text(),
                            "error": page.locator("#error").inner_text(),
                        }
                        found, issues = check_ui(task["queries"], state)
                        expected = expected_for_seeded_fixture(task["mode"], task["queries"])
                        row = {
                            **task,
                            "seeded_family": infer_seeded_family(task["queries"]),
                            "observed_violation": found,
                            "seeded_expected_violation": expected,
                            "as_expected": found == expected,
                            "issues": issues,
                            "ui_state": state,
                            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
                        }
                        rows.append(row)
                        mark = "PASS" if row["as_expected"] else "CHECK"
                        print(f"[{mark}] {number}/{len(tasks)} {task['strategy']} "
                              f"{task['mode']} {task['queries']} violation={found}")
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)

    summary = summarize(rows)
    result = {
        "project": "WebStateCheck Day 3 — Guided vs Random Synthetic Comparison",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "One synthetic instrumented fixture only; NOT real-world or AI evaluation",
        "seed": seed,
        "repeats": repeats,
        "summary": summary,
        "observations": rows,
    }
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    (results / "day3_observations.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Day 3 — Guided vs random selection (synthetic-only)", "",
        "**Warning:** This compares test *selection* on one intentionally buggy application. "
        "It is not evidence of real-world generalization, AI performance, or novelty.", "",
        f"Seed: `{seed}`; repetitions: `{repeats}`. Each strategy receives "
        f"**{4 * repeats} scenario executions per app version**.", "",
        "| Strategy | Query actions / version | Buggy violations | Fixed violations | Seeded bug families exercised | Agreement | Mean ms/check |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for name in ("guided", "random"):
        item = summary[name]
        family = ", ".join(item["known_bug_families_exercised"]) or "none"
        lines.append(
            f"| {name} | {item['query_actions_per_version']} | {item['buggy_violations']} | {item['fixed_violations']} | "
            f"{family} | {item['matches_seeded_expectations']}/{item['total_checks']} | "
            f"{item['mean_elapsed_ms']:.1f} |"
        )
    lines += [
        "", "## Interpretation", "",
        "- **Guided** uses four known scenario families from Day 2; it has prior knowledge of this fixture.",
        "- **Random** chooses one or two query actions without targeting bug categories.",
        "- Both approaches use the **same** application-specific UI oracle. This comparison is of input selection only.",
        "- The `seeded_family` label is determined only after sampling and is used for analysis, not detection.",
        "- The visible UI oracle checks state after an instrumented internal completion counter; this is not portable to real websites.",
        "- One synthetic app and repeated random seeds do not establish detector accuracy or a general research contribution.",
        "", "## Next research steps", "",
        "1. Reproduce one independently documented bug/fix pair from a public JavaScript project.",
        "2. Design observable completion criteria that do not depend on `window.__research`.",
        "3. Compare against published AJAX race detectors / UI testing methods where reproducible.",
        "4. Only after these baselines, test whether AI-assisted candidate selection improves coverage per test budget.", "",
    ]
    (results / "day3_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nSaved: " + str(results / "day3_summary.md"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261118)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be between 1 and 100")
    result = run(args.repeats, args.seed)
    if any(group["matches_seeded_expectations"] != group["total_checks"]
           for group in result["summary"].values()):
        print("NOTE: Some observations differ from simple seeded labels. "
              "Investigate results/day3_observations.json; fast-request timing can vary.")


if __name__ == "__main__":
    main()
