"""Day 11: audit Day 10 observations, freeze prospective evaluation protocol.

This audits development-only evidence. It DOES NOT generate new experiments or
claim that an LLM found a real-world defect.

Usage:
  python -m webstatecheck.day11_audit audit
  python -m webstatecheck.day11_audit freeze
  python -m webstatecheck.day11_audit verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day3_baseline import check_ui
from webstatecheck.day9_plans import get_path, validate_plan

ROOT = Path(__file__).resolve().parent.parent
METHODS = ("random", "heuristic", "llm")
PROTOCOL = ROOT / "research" / "DAY11_HELDOUT_PROTOCOL.md"
LOCK = ROOT / "research" / "day11_future_protocol_lock.json"
FROZEN = (
    "webstatecheck/day3_baseline.py",
    "webstatecheck/day4_portable.py",
    "webstatecheck/day9_plans.py",
    "webstatecheck/day10_compare.py",
    "webstatecheck/day11_audit.py",
    "research/day9_candidates/random.json",
    "research/day9_candidates/heuristic.json",
    "research/day9_candidates/llm.json",
    "research/DAY11_HELDOUT_PROTOCOL.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root: Path = ROOT) -> dict:
    """Validate saved fixture trials against their own UI oracle and plan hashes."""
    methods = {}
    combined = []
    for method in METHODS:
        plan_path = get_path(method, root)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        budget = validate_plan(plan, method)
        path = root / "results" / f"day9_{method}_observations.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("method") != method or payload.get("plan_sha256") != digest(plan_path):
            raise ValueError(f"Plan identity/hash mismatch for {method}")
        if payload.get("scenarios_per_version") != 4 or payload.get("actions_per_version") != 8:
            raise ValueError(f"Unexpected execution budget for {method}")
        records = payload.get("observations")
        if not isinstance(records, list) or len(records) != 8:
            raise ValueError(f"Expected 8 observations for {method}")
        planned = {p["plan_id"]: p["queries"] for p in plan["plans"]}
        for mode in ("buggy", "fixed"):
            observed = [r for r in records if r.get("mode_for_analysis_only") == mode]
            if len(observed) != 4:
                raise ValueError(f"Expected 4 observations of {method}/{mode}")
            if {r.get("plan_id") for r in observed} != set(planned):
                raise ValueError(f"Plan IDs missing or repeated: {method}/{mode}")
            for record in observed:
                if record.get("queries") != planned[record["plan_id"]]:
                    raise ValueError(f"Plan actions mismatch: {method}/{record['plan_id']}")
                verdict = record.get("verdict")
                if verdict not in {"clear", "violation", "inconclusive"}:
                    raise ValueError("Unknown verdict")
                if verdict != "inconclusive":
                    expected_found, expected_issues = check_ui(record["queries"], record["ui_state"])
                    expected_verdict = "violation" if expected_found else "clear"
                    if verdict != expected_verdict or sorted(record.get("issues", [])) != sorted(expected_issues):
                        raise ValueError(f"Oracle mismatch: {method}/{mode}/{record['plan_id']}")
                combined.append({"method": method, "mode": mode, "plan_id": record["plan_id"],
                                 "queries": record["queries"], "verdict": verdict,
                                 "issues": record.get("issues", [])})
        buggy = [r for r in records if r.get("mode_for_analysis_only") == "buggy"]
        fixed = [r for r in records if r.get("mode_for_analysis_only") == "fixed"]
        methods[method] = {
            "scenario_budget_per_version": budget["scenarios"],
            "action_budget_per_version": budget["actions"],
            "buggy_violations": sum(r["verdict"] == "violation" for r in buggy),
            "fixed_violations": sum(r["verdict"] == "violation" for r in fixed),
            "inconclusive": sum(r["verdict"] == "inconclusive" for r in records),
            "observed_issue_labels": dict(Counter(issue for r in buggy for issue in r.get("issues", []))),
            "plan_sha256": digest(plan_path),
            "observations_sha256": digest(path),
        }
    return {
        "study": "Day 11 retrospective evidence audit — Day 10 SYNTHETIC DEVELOPMENT ONLY",
        "claims_not_supported": ["AI superiority", "blinded evaluation", "generalized accuracy",
                                 "new real-world defect discovery", "independently confirmed unique defects"],
        "methods": methods, "observation_count": len(combined), "records": combined,
    }


def report_md(info: dict) -> str:
    lines = ["# Day 11 — Day 10 evidence audit", "",
             "**Retrospective audit of a familiar synthetic fixture, NOT a new experiment or a held-out AI benchmark.**", "",
             f"Audited observations: **{info['observation_count']}** (three methods × two versions × four scenarios).", "",
             "| Method | Scenarios / version | Actions / version | Buggy violations | Fixed violations | Inconclusive | Recorded issue labels |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for method in METHODS:
        item = info["methods"][method]
        labels = ", ".join(f"{k} ({v})" for k, v in sorted(item["observed_issue_labels"].items())) or "none"
        lines.append(f"| {method} | {item['scenario_budget_per_version']} | {item['action_budget_per_version']} | "
                     f"{item['buggy_violations']} | {item['fixed_violations']} | {item['inconclusive']} | {labels} |")
    lines.extend(["", "## Interpretation", "",
                  "- AI candidate is **context-contaminated**: the model already knew the fixture and earlier results.",
                  "- Issue labels (e.g., `unexpected_error`) are **oracle categories**, not separately confirmed bugs.",
                  "- This audit rechecks plan hashes, budgets, unique scenario IDs and recorded verdicts against the UI oracle.",
                  "- This audit **does not** validate that the oracle is correct, that failures are independent, or that AI is better.",
                  "- Execution time excludes model token costs and generation latency.",
                  "", "## Prospective study", "",
                  "See `research/DAY11_HELDOUT_PROTOCOL.md`. Freeze it **before** selecting and inspecting new evaluation defects.", ""])
    return "\n".join(lines)


def freeze(root: Path = ROOT, timestamp: str | None = None) -> dict:
    """Freeze future protocol and existing runner/candidates. No rewriting a prior lock."""
    lock = root / "research" / "day11_future_protocol_lock.json"
    if lock.exists():
        raise FileExistsError(f"Protocol lock already exists: {lock}. Run verify instead.")
    # Before locking prospective study, confirm existing evidence is coherent.
    audit(root)
    files = {}
    for rel in FROZEN:
        path = root / rel
        files[rel] = digest(path)
    value = {
        "label": "PROSPECTIVE FUTURE protocol only; not a claim Day 10 was blinded",
        "frozen_utc": timestamp or datetime.now(timezone.utc).isoformat(),
        "prior_development_data": "All Day 1–10 results are exploratory and excluded from holdout scoring",
        "file_sha256": files,
        "holdout_status": "NOT SELECTED / NOT EVALUATED",
    }
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return value


def verify(root: Path = ROOT) -> list[str]:
    payload = json.loads((root / "research" / "day11_future_protocol_lock.json").read_text(encoding="utf-8"))
    drift = []
    for rel, expected in payload["file_sha256"].items():
        p = root / rel
        if not p.exists() or digest(p) != expected:
            drift.append(rel)
    return drift


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "freeze", "verify"))
    args = parser.parse_args()
    try:
        if args.command == "audit":
            result = audit()
            out = ROOT / "results"
            out.mkdir(parents=True, exist_ok=True)
            (out / "day11_evidence_audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            path = out / "day11_evidence_audit.md"
            path.write_text(report_md(result), encoding="utf-8")
            print(report_md(result))
            print("Saved:", path)
        elif args.command == "freeze":
            lock = freeze()
            print("Frozen prospective study protocol:", LOCK)
            print("Tracked file hashes:", len(lock["file_sha256"]))
            print("No held-out experiments have been run.")
        else:
            delta = verify()
            if delta:
                print("PROTOCOL DRIFT:", *delta, sep="\n  - ")
                raise SystemExit(2)
            print("Verified: all frozen files are unchanged.")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        parser.exit(1, f"Day 11: {e}\n")


if __name__ == "__main__":
    main()
