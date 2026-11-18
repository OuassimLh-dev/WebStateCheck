"""Reproducible browser experiments; never assumes a bug exists without checking.

Run: python -m webstatecheck.experiment --repeats 3
Outputs: results/observations.json and results/summary.md
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from .server import create_server

ROOT = Path(__file__).resolve().parent.parent


def perform(page, case: str) -> dict:
    start = time.monotonic()
    if case == "stale_response":
        # Ensure two requests start before either completes, then wait for both.
        page.locator("#query").fill("old")
        page.locator("#search").click()
        page.locator("#query").fill("new")
        page.locator("#search").click()
        page.wait_for_function("window.__research.completed.length === 2", timeout=10000)
        actual = page.locator("#results").inner_text()
        violated = actual != "Results for: new"
        evidence = {"actual_results": actual, "expected_results": "Results for: new"}
    elif case == "stuck_loading":
        page.locator("#query").fill("fail")
        page.locator("#search").click()
        page.wait_for_function("window.__research.completed.length === 1", timeout=10000)
        actual = page.locator("#status").inner_text()
        err = page.locator("#error").inner_text()
        violated = bool(actual.strip())
        evidence = {"loading_text_after_failure": actual, "error_text": err}
    elif case == "normal_success":
        page.locator("#query").fill("hello")
        page.locator("#search").click()
        page.wait_for_function("window.__research.completed.length === 1", timeout=10000)
        res = page.locator("#results").inner_text()
        loading = page.locator("#status").inner_text()
        violated = res != "Results for: hello" or bool(loading.strip())
        evidence = {"results": res, "loading_text": loading}
    else:
        raise ValueError(case)
    return {"case": case, "violation_detected": violated,
            "evidence": evidence, "elapsed_ms": round((time.monotonic() - start) * 1000, 2)}


def run(repeats: int = 3):
    rows = []
    httpd = create_server(port=0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            # On systems with a system Chromium, use it; on macOS, use the
            # browser installed with `python -m playwright install chromium`.
            executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium")
            kwargs = {"headless": True, "channel": "chromium"}
            if executable:
                kwargs["executable_path"] = executable
            browser = playwright.chromium.launch(**kwargs)
            try:
                for repeat in range(1, repeats + 1):
                    for mode in ("buggy", "fixed"):
                        for case in ("stale_response", "stuck_loading", "normal_success"):
                            context = browser.new_context(service_workers="block")
                            try:
                                page = context.new_page()
                                page.goto(f"http://127.0.0.1:{port}/?mode={mode}")
                                result = perform(page, case)
                                expected = mode == "buggy" and case != "normal_success"
                                rows.append({"repeat": repeat, "mode": mode,
                                             "expected_violation": expected,
                                             **result, "as_expected": result["violation_detected"] == expected})
                            finally:
                                context.close()
            finally:
                browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)

    output = ROOT / "results"
    output.mkdir(exist_ok=True)
    payload = {
        "project": "WebStateCheck", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Controlled synthetic fixtures; not real-world evidence; no AI integrated yet",
        "repeats": repeats, "observations": rows,
        "matching_expectations": sum(r["as_expected"] for r in rows), "total": len(rows),
    }
    (output / "observations.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = ["# WebStateCheck baseline observations", "", "**Scope:** Synthetic fixtures deliberately seeded with two bugs. These are engineering checks, not evidence of effectiveness on real websites.", "",
             f"Runs matching intended fixture behavior: **{payload['matching_expectations']}/{payload['total']}**", "", "| Trial | Mode | Case | Violation? | Expected? | Elapsed ms |", "|---|---|---|---|---|---:|"]
    for r in rows:
        lines.append(f"| {r['repeat']} | {r['mode']} | {r['case']} | {r['violation_detected']} | {r['expected_violation']} | {r['elapsed_ms']:.1f} |")
    lines += ["", "## Next steps", "", "1. Expand to independently sourced, real-world bug/fix pairs.", "2. Introduce a separately evaluated static-analysis baseline.", "3. Generate candidate tests with an LLM and verify them with deterministic browser oracles.", "4. Compare precision, recall, coverage, false positives, and cost across methods.", ""]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    for r in rows:
        label = "PASS" if r["as_expected"] else "CHECK"
        print(f"[{label}] repeat={r['repeat']} mode={r['mode']} case={r['case']} observed_violation={r['violation_detected']}")
    print(f"\n{payload['matching_expectations']}/{payload['total']} checks behaved as expected")
    print(f"Saved: {output / 'observations.json'}")
    print(f"Saved: {output / 'summary.md'}")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3, help="Number of repeats (1 to 100)")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be between 1 and 100")
    outcome = run(args.repeats)
    if outcome["matching_expectations"] != outcome["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
