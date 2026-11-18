"""Day 2: seeded exploration of asynchronous UI invariants.

Run from the WebStateCheck project root:
    python -m webstatecheck.exploration --repeats 5 --seed 20261118

This is a synthetic test-harness experiment, not an AI method or a
real-world benchmark. It reuses the intentionally seeded local fixture.
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
from typing import Any

from .server import create_server

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("single_success", "request_failure", "overlap_stale", "overlap_control")
FAST_QUERIES = ("new", "hello", "alpha", "beta")


def make_scenarios(repeats: int, seed: int) -> list[dict[str, Any]]:
    """Produce matched, seeded scenarios to evaluate both application versions."""
    if not 1 <= repeats <= 100:
        raise ValueError("repeats must be between 1 and 100")
    rng = random.Random(seed)
    result = []
    for trial in range(1, repeats + 1):
        kinds = list(KINDS)
        rng.shuffle(kinds)
        for kind in kinds:
            if kind == "single_success":
                queries = [rng.choice(FAST_QUERIES)]
            elif kind == "request_failure":
                queries = ["fail"]
            elif kind == "overlap_stale":
                queries = ["old", rng.choice(FAST_QUERIES)]
            else:
                queries = [rng.choice(FAST_QUERIES), "old"]
            result.append({"trial": trial, "kind": kind, "queries": queries})
    return result


def expected_violation(mode: str, kind: str) -> bool:
    """Ground truth of this known seeded application, not detector input."""
    if mode not in ("buggy", "fixed") or kind not in KINDS:
        raise ValueError("Unrecognized mode or scenario kind")
    return mode == "buggy" and kind in ("request_failure", "overlap_stale")


def evaluate_ui(kind: str, queries: list[str], state: dict[str, str]) -> tuple[bool, list[str]]:
    """A UI-only oracle: checks observable result, error and loading text.

    Does not use a fixture mode or known expected defects.
    """
    reasons = []
    loading = state["loading"].strip()
    error = state["error"].strip()
    result = state["results"].strip()
    if loading:
        reasons.append("loading_indicator_remained_visible")
    if kind == "request_failure":
        if not error:
            reasons.append("failure_not_reported")
    else:
        expected_result = f"Results for: {queries[-1]}"
        if result != expected_result:
            reasons.append("results_did_not_match_latest_query")
        if error:
            reasons.append("unexpected_error")
    return bool(reasons), reasons


def _launch_browser(playwright):
    """Use installed full Chromium when headless shell is unavailable."""
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium")
    if executable:
        return playwright.chromium.launch(headless=True, executable_path=executable)
    # channel='chromium' chooses full Chromium in newer Playwright versions,
    # avoiding a separate chrome-headless-shell download on the user's Mac.
    return playwright.chromium.launch(headless=True, channel="chromium")


def run(repeats: int, seed: int) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright  # optional until experiment runs

    scenarios = make_scenarios(repeats, seed)
    rows: list[dict[str, Any]] = []
    server = create_server(port=0)
    port = server.server_address[1]
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            try:
                for scenario in scenarios:
                    for mode in ("buggy", "fixed"):
                        context = browser.new_context(service_workers="block")
                        started = time.monotonic()
                        try:
                            page = context.new_page()
                            page.goto(f"http://127.0.0.1:{port}/?mode={mode}")
                            for query in scenario["queries"]:
                                page.locator("#query").fill(query)
                                page.locator("#search").click()
                            page.wait_for_function(
                                "count => window.__research.completed.length === count",
                                arg=len(scenario["queries"]), timeout=10000,
                            )
                            # The fixture's completion counter is a synchronization
                            # aid only. Violations are evaluated from visible UI.
                            page.wait_for_timeout(30)
                            state = {
                                "loading": page.locator("#status").inner_text(),
                                "error": page.locator("#error").inner_text(),
                                "results": page.locator("#results").inner_text(),
                            }
                            violated, reasons = evaluate_ui(
                                scenario["kind"], scenario["queries"], state
                            )
                            expected = expected_violation(mode, scenario["kind"])
                            row = {
                                **scenario, "mode": mode,
                                "observed_violation": violated,
                                "expected_violation": expected,
                                "as_expected": violated == expected,
                                "reasons": reasons,
                                "ui_state": state,
                                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                            }
                            rows.append(row)
                            mark = "PASS" if row["as_expected"] else "CHECK"
                            print(f"[{mark}] trial={row['trial']} {mode} {row['kind']} "
                                  f"queries={row['queries']} violation={violated}")
                        finally:
                            context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)

    matrix = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for row in rows:
        if row["observed_violation"] and row["expected_violation"]:
            matrix["TP"] += 1
        elif not row["observed_violation"] and not row["expected_violation"]:
            matrix["TN"] += 1
        elif row["observed_violation"]:
            matrix["FP"] += 1
        else:
            matrix["FN"] += 1

    output = ROOT / "results"
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "WebStateCheck Day 2 Exploration",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Only synthetic buggy/fixed variants of one application; not real-world evidence or AI evaluation",
        "seed": seed, "repeats": repeats, "scenarios_per_repeat": len(KINDS),
        "observations": rows, "synthetic_confusion_matrix": matrix,
        "matching_expectations": sum(r["as_expected"] for r in rows),
        "total": len(rows),
    }
    (output / "day2_observations.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Day 2 — Seeded scenario exploration", "",
        "**Evidence level:** Controlled synthetic fixture only. Not independent detection accuracy, not AI results.", "",
        f"Seed: `{seed}` · Repetitions: `{repeats}` · Scenario types: `{len(KINDS)}`", "",
        f"Expected behavior matched: **{payload['matching_expectations']}/{payload['total']}**", "",
        "## Synthetic-only confusion matrix", "",
        "| True positives | True negatives | False positives | False negatives |",
        "|---:|---:|---:|---:|",
        f"| {matrix['TP']} | {matrix['TN']} | {matrix['FP']} | {matrix['FN']} |", "",
        "This matrix only measures agreement with **deliberately seeded** defect labels.",
        "It must not be presented as general bug-detection precision or recall.", "",
        "## Observations", "",
        "| Trial | Mode | Scenario | Input sequence | Violation | Expected | Elapsed ms |",
        "|---:|---|---|---|---|---|---:|",
    ]
    for row in rows:
        sequence = " → ".join(row["queries"])
        lines.append(f"| {row['trial']} | {row['mode']} | {row['kind']} | {sequence} | "
                     f"{row['observed_violation']} | {row['expected_violation']} | {row['elapsed_ms']:.1f} |")
    lines += ["", "## Interpretation", "",
              "- An observable UI-state oracle is applied without consulting the application's mode.",
              "- Scenario families are still hand-selected for our known fixture; this is not autonomous discovery.",
              "- Counter synchronization uses an instrumented local fixture and is not yet portable to arbitrary websites.",
              "- Next: independently sourced bug/fix pairs, then static and AI scenario-generation baselines.", ""]
    (output / "day2_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{payload['matching_expectations']}/{payload['total']} synthetic checks matched expected behavior")
    print(f"Saved: {output / 'day2_summary.md'}")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261118)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be between 1 and 100")
    outcome = run(args.repeats, args.seed)
    if outcome["matching_expectations"] != outcome["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
