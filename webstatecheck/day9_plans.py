"""Day 9: budget-matched TEST-PLAN protocol (development fixture ONLY).

This is not an AI detector. An LLM candidate must be generated separately and
its provenance logged. Known fixture and prior issue knowledge prohibit using
these results to claim blinded effectiveness or generalization.

Commands:
  python -m webstatecheck.day9_plans prepare --seed 20261118
  python -m webstatecheck.day9_plans validate --method random
  python -m webstatecheck.day9_plans run --method random
  python -m webstatecheck.day9_plans run --method heuristic
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "research" / "day9_candidates"
RESULTS = ROOT / "results"
TARGET_ID = "local-search-development-only"
QUERIES = ("old", "new", "hello", "alpha", "beta", "fail")
PLAN_COUNT = 4
ACTIONS_PER_PLAN = 2


def canonical_json(x: object) -> bytes:
    return (json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_path(method: str, root: Path = ROOT) -> Path:
    if method not in {"random", "heuristic", "llm"}:
        raise ValueError("Method must be random, heuristic or llm")
    return root / "research" / "day9_candidates" / f"{method}.json"


def validate_plan(payload: object, expected_method: str | None = None) -> dict:
    """Do not trust plan files: require the exact public action grammar and budget."""
    if not isinstance(payload, dict):
        raise ValueError("Plan must be a JSON object")
    if set(payload) != {"target_id", "method", "generator", "plans"}:
        raise ValueError("Required top-level keys: target_id, method, generator, plans")
    method = payload["method"]
    if method not in {"random", "heuristic", "llm"} or (expected_method and method != expected_method):
        raise ValueError("Method is invalid or disagrees with --method")
    if payload["target_id"] != TARGET_ID:
        raise ValueError("Unexpected target_id")
    g = payload["generator"]
    if not isinstance(g, dict) or not all(isinstance(g.get(k), str) and g[k].strip() for k in ("name", "recorded_utc")):
        raise ValueError("generator.name and generator.recorded_utc are required")
    if method == "llm" and not all(isinstance(g.get(k), str) and g[k].strip() for k in ("model", "prompt_sha256")):
        raise ValueError("LLM plans additionally require generator.model and generator.prompt_sha256")
    plans = payload["plans"]
    if not isinstance(plans, list) or len(plans) != PLAN_COUNT:
        raise ValueError(f"Exactly {PLAN_COUNT} plans are required")
    ids = []
    for p in plans:
        if not isinstance(p, dict) or set(p) != {"plan_id", "queries"}:
            raise ValueError("Each plan must contain ONLY plan_id and queries")
        if not isinstance(p["plan_id"], str) or not p["plan_id"].strip() or len(p["plan_id"]) > 80:
            raise ValueError("plan_id must be a nonblank string <= 80 characters")
        ids.append(p["plan_id"])
        q = p["queries"]
        if not isinstance(q, list) or len(q) != ACTIONS_PER_PLAN or any(not isinstance(v, str) or v not in QUERIES for v in q):
            raise ValueError(f"Each plan needs exactly {ACTIONS_PER_PLAN} search actions from {QUERIES}")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate plan_id")
    return {"method": method, "scenarios": PLAN_COUNT, "actions": PLAN_COUNT * ACTIONS_PER_PLAN}


def prepare(root: Path = ROOT, seed: int = 20261118, force: bool = False) -> dict:
    """Create reproducible development baselines without overwriting prior candidates."""
    out = root / "research" / "day9_candidates"
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    random_q = [[rng.choice(QUERIES), rng.choice(QUERIES)] for _ in range(PLAN_COUNT)]
    # Fixed illustrative heuristics; intentionally informed by synthetic fixture behavior.
    heuristic_q = [["old", "new"], ["fail", "hello"], ["new", "old"], ["alpha", "fail"]]
    files = {}
    for method, sequences in (("random", random_q), ("heuristic", heuristic_q)):
        path = get_path(method, root)
        if path.exists() and not force:
            raise FileExistsError(f"{path} already exists; no overwrite. Use --force only if you intend to replace it.")
        payload = {
            "target_id": TARGET_ID, "method": method,
            "generator": {"name": "python-random-seeded" if method == "random" else "hand-authored-demo-heuristic", "recorded_utc": datetime.now(timezone.utc).isoformat(), "seed": str(seed)},
            "plans": [{"plan_id": f"{method}-{i:02d}", "queries": q} for i, q in enumerate(sequences, 1)],
        }
        validate_plan(payload, method)
        path.write_bytes(canonical_json(payload))
        files[method] = {"path": str(path), "sha256": sha256(path), "plans": PLAN_COUNT, "actions": PLAN_COUNT * ACTIONS_PER_PLAN}
    return files


def evaluate_browser(root: Path, method: str, payload: dict) -> dict:
    """Run existing fixture using exactly the same runner/oracle for each strategy."""
    from playwright.sync_api import sync_playwright
    from webstatecheck.day3_baseline import check_ui
    from webstatecheck.day4_portable import _launch_browser, wait_for_search_requests
    from webstatecheck.server import create_server

    server = create_server(port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_address[1]
    raw = []
    try:
        with sync_playwright() as playwright:
            browser = _launch_browser(playwright)
            try:
                for mode in ("buggy", "fixed"):
                    for p in payload["plans"]:
                        context = browser.new_context(service_workers="block")
                        started = time.monotonic()
                        try:
                            page = context.new_page()
                            page.goto(f"http://127.0.0.1:{port}/?mode={mode}")
                            completion = wait_for_search_requests(page, p["queries"])
                            state = {"results":page.locator("#results").inner_text(),
                                     "loading":page.locator("#status").inner_text(),
                                     "error":page.locator("#error").inner_text()}
                            inconclusive = completion["timed_out"] or completion["requestfailed_count"] > 0
                            violation, issues = (False, []) if inconclusive else check_ui(p["queries"], state)
                            verdict = "inconclusive" if inconclusive else "violation" if violation else "clear"
                            r = {"method": method, "mode_for_analysis_only": mode,
                                 "plan_id":p["plan_id"], "queries":p["queries"],
                                 "verdict":verdict, "issues":issues, "completion":completion,
                                 "ui_state":state, "elapsed_ms": round((time.monotonic()-started)*1000, 1)}
                            raw.append(r)
                            print(f'[{verdict.upper()}] {method} {mode} {p["plan_id"]}: {p["queries"]}')
                        finally:
                            context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
    tally = {}
    for mode in ("buggy", "fixed"):
        group = [r for r in raw if r["mode_for_analysis_only"] == mode]
        tally[mode] = {"violations":sum(r["verdict"]=="violation" for r in group),
                       "clear":sum(r["verdict"]=="clear" for r in group),
                       "inconclusive":sum(r["verdict"]=="inconclusive" for r in group),
                       "unique_issue_types":sorted({issue for r in group for issue in r["issues"]}),
                       "mean_ms":round(mean(r["elapsed_ms"] for r in group), 1)}
    return {"method":method,"target_id":TARGET_ID,"evidence_level":"DEVELOPMENT SYNTHETIC ONLY — NOT BLIND OR AI EFFECTIVENESS",
            "plan_sha256":sha256(get_path(method, root)), "scenarios_per_version":PLAN_COUNT,
            "actions_per_version":PLAN_COUNT*ACTIONS_PER_PLAN,"summary":tally,"observations":raw}


def write_report(result: dict, root: Path) -> Path:
    out = root / "results"
    out.mkdir(exist_ok=True)
    stem = f'day9_{result["method"]}'
    (out / f"{stem}_observations.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    rows = [f'# Day 9 — {result["method"]} plan execution', '',
            '**Evidence: synthetic development fixture only; plans may contain prior bug knowledge. Not a blinded comparison.**', '',
            f'Plan file SHA-256: `{result["plan_sha256"]}`', '',
            f'Budget: {result["scenarios_per_version"]} plans × 2 queries = {result["actions_per_version"]} actions per version.', '',
            '| Mode | Violations | Clear | Inconclusive | Unique issue types | Mean ms/check |',
            '|---|---:|---:|---:|---|---:|']
    for mode, vals in result["summary"].items():
        rows.append(f'| {mode} | {vals["violations"]} | {vals["clear"]} | {vals["inconclusive"]} | {", ".join(vals["unique_issue_types"]) or "—"} | {vals["mean_ms"]} |')
    rows += ['', 'The generator did not see revision labels through the schema, but the development fixture is known to the research team.',
             'No real-world defect discovery or LLM superiority claim is supported by these results.', '']
    path = out / f"{stem}_summary.md"
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--seed", type=int, default=20261118)
    prep.add_argument("--force", action="store_true")
    valid = sub.add_parser("validate")
    valid.add_argument("--method", choices=("random","heuristic","llm"), required=True)
    run = sub.add_parser("run")
    run.add_argument("--method", choices=("random","heuristic","llm"), required=True)
    args = ap.parse_args()
    try:
        if args.command == "prepare":
            print(json.dumps(prepare(seed=args.seed, force=args.force), indent=2))
            return
        path = get_path(args.method)
        payload = json.loads(path.read_text(encoding="utf-8"))
        print("Validated:", validate_plan(payload, args.method), "SHA-256:", sha256(path))
        if args.command == "run":
            report = write_report(evaluate_browser(ROOT, args.method, payload), ROOT)
            print("Saved:", report)
    except (FileNotFoundError, FileExistsError, ValueError, KeyError, json.JSONDecodeError) as exc:
        ap.exit(1, f"Day 9: {exc}\n")


if __name__ == "__main__":
    main()
