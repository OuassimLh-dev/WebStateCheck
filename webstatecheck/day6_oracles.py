"""Day 6: declarative state invariants on saved Day 4 and Day 5 observations.

Use: python -m webstatecheck.day6_oracles

Evaluation NEVER reads buggy/fixed labels. The adapters DO encode application
semantics (search-result text, Final Form's pending-validator condition).
Therefore this is an engineering prototype, not domain-independent detection.
No LLM, no new external experiments, and no novelty claims.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES = ROOT / "research" / "oracles" / "day6_rules.json"
MISSING = object()
ALLOWED_OPS = {"eq", "ne", "nonempty", "empty"}


def check_condition(facts: dict[str, Any], condition: dict[str, Any]) -> bool | None:
    """Return True/False or None if a required observation is missing."""
    key = condition.get("field")
    op = condition.get("op")
    if not isinstance(key, str) or op not in ALLOWED_OPS:
        raise ValueError(f"Invalid condition: {condition}")
    observed = facts.get(key, MISSING)
    if observed is MISSING or observed is None:
        return None
    if op in ("eq", "ne"):
        if "value" not in condition:
            raise ValueError(f"Condition must include a value: {condition}")
        equals = type(observed) is type(condition["value"]) and observed == condition["value"]
        return equals if op == "eq" else not equals
    if op == "empty":
        return observed == "" or observed == []
    return observed != "" and observed != []


def evaluate_rules(source: str, facts: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute a verdict without seeing revision or known defect labels."""
    outcomes: list[dict[str, str]] = []
    for rule in rules:
        if rule.get("source") != source:
            continue
        triggers = [check_condition(facts, c) for c in rule["when"]]
        if False in triggers:
            status = "not_applicable"
        elif None in triggers:
            status = "inconclusive"
        else:
            assertions = [check_condition(facts, c) for c in rule["require"]]
            status = "violation" if False in assertions else "inconclusive" if None in assertions else "clear"
        outcomes.append({"rule": rule["id"], "status": status})

    statuses = [x["status"] for x in outcomes]
    if "violation" in statuses:
        verdict = "violation"
    elif "inconclusive" in statuses:
        verdict = "inconclusive"
    elif "clear" in statuses:
        verdict = "clear"
    else:
        verdict = "not_covered"
    return {"verdict": verdict, "rules": outcomes}


def browser_facts(row: dict[str, Any]) -> dict[str, Any]:
    """Fixture adapter. Searches/expected-result format are app-specific."""
    ui = row.get("ui_state") or {}
    completion = row.get("completion") or {}
    queries = row.get("queries") or []
    last = queries[-1] if queries else None
    results = ui.get("results")
    error = ui.get("error")
    loading = ui.get("loading")
    statuses = completion.get("http_statuses")
    return {
        "error_visible": bool(error.strip()) if isinstance(error, str) else None,
        "loading_visible": bool(loading.strip()) if isinstance(loading, str) else None,
        "network_settled": (
            not completion["timed_out"] and completion.get("requestfailed_count", 0) == 0
        ) if "timed_out" in completion else None,
        "latest_query_is_success": (last != "fail") if last is not None else None,
        "result_matches_latest_query": (
            results == f"Results for: {last}"
        ) if last is not None and isinstance(results, str) else None,
        "http_error_seen": any(s >= 400 for s in statuses) if isinstance(statuses, list) else None,
    }


def final_form_facts(row: dict[str, Any]) -> dict[str, Any]:
    """One documented probe phase: older validation done, newer still pending."""
    value = (row.get("after_older_resolved") or {}).get("validating")
    return {
        "newer_validation_pending": True,  # Guaranteed by Day 5 probe's chosen observation point.
        "validating": value if isinstance(value, bool) else None,
    }


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def validate_rules(rules: list[dict[str, Any]]) -> None:
    ids = [r.get("id") for r in rules]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate rule identifiers")
    for rule in rules:
        if rule.get("source") not in {"browser", "final_form"}:
            raise ValueError("Unknown source")
        if not rule.get("when") or not rule.get("require"):
            raise ValueError("Each rule needs when and require clauses")
        for clause in rule["when"] + rule["require"]:
            check_condition({clause.get("field", ""): True}, clause)


def run(day4: Path, day5: Path, rules_file: Path, output: Path) -> dict[str, Any]:
    configuration = load_json(rules_file)
    rules = configuration["rules"]
    validate_rules(rules)
    browser = load_json(day4)["observations"]
    form = load_json(day5)["observations"]
    observations = []
    for index, raw in enumerate(browser, 1):
        # Only post-hoc comparison uses the saved mode and prior verdict.
        assessment = evaluate_rules("browser", browser_facts(raw), rules)
        observations.append({
            "id": f"browser-{index}", "source": "browser",
            "verdict": assessment["verdict"], "rule_results": assessment["rules"],
            "known_version_for_analysis_only": raw.get("mode"),
            "prior_verdict_for_analysis_only": "inconclusive" if raw.get("inconclusive") else "violation" if raw.get("observed_violation") else "clear",
            "strategy_for_analysis_only": raw.get("strategy"),
        })
    for index, raw in enumerate(form, 1):
        assessment = evaluate_rules("final_form", final_form_facts(raw), rules)
        observations.append({
            "id": f"final-form-{index}", "source": "final_form",
            "verdict": assessment["verdict"], "rule_results": assessment["rules"],
            "known_version_for_analysis_only": raw.get("label"),
            "prior_verdict_for_analysis_only": "violation" if raw.get("violation") else "clear",
            "commit_for_provenance": raw.get("upstream_commit"),
        })

    group_counts: dict[str, dict[str, int]] = {}
    for src in ("browser", "final_form"):
        subset = [r for r in observations if r["source"] == src]
        group_counts[src] = dict(Counter(r["verdict"] for r in subset))
    disagreements = [r for r in observations if r["verdict"] != r["prior_verdict_for_analysis_only"]]
    data = {
        "study": "Day 6: same declarative checker, two application-specific adapters",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "method": "hand-specified invariants; re-evaluation of existing observations; not new experiments or AI discovery",
        "input_paths": [str(day4), str(day5)],
        "counts": group_counts,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "observations": observations,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "day6_oracle_observations.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Day 6 — Reusable state-invariant checking prototype", "",
        "**Evidence:** Reanalysis of Day 4 synthetic browser results and Day 5 pinned Final Form source reproduction. No new trials or AI.", "",
        "| Source | Cases | Violations | Clear | Inconclusive | Not covered |", "|---|---:|---:|---:|---:|---:|",
    ]
    for src, label in (("browser", "Synthetic browser"), ("final_form", "Final Form (upstream)")):
        counts = group_counts[src]
        n = sum(counts.values())
        lines.append(f'| {label} | {n} | {counts.get("violation", 0)} | {counts.get("clear", 0)} | {counts.get("inconclusive", 0)} | {counts.get("not_covered", 0)} |')
    lines += [
        "", f"**Differences from prior targeted oracle verdicts:** {len(disagreements)}.",
        "Differences can reflect missing coverage, differences in the oracle specification, or an implementation issue; they are not automatically false positives or negatives.",
        "", "## Constraints", "",
        "- The checker is generic, but the two input adapters and invariant rules are hand-written with application knowledge.",
        "- A 'not covered' case has no applicable rule; it is not a confirmed clean run.",
        "- This report reuses existing measurements. No independent detection experiment is performed.",
        "- For Final Form, the 'newer validation pending' fact follows from the deliberately controlled probe timing, not independent inference.",
        "- Before claiming transferability, add several independent projects, browser-native observations and blinded evaluation.",
        "", "## Next research action", "",
        "Select a second public bug/fix pair independently, pin commits, reproduce it with a fresh adapter, and report failures as well as successes.",
    ]
    if disagreements:
        lines += ["", "## First disagreements", ""]
        for r in disagreements[:8]:
            lines.append(f'- {r["id"]}: prior `{r["prior_verdict_for_analysis_only"]}`, declarative `{r["verdict"]}`')
    (output / "day6_oracle_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day4", type=Path, default=ROOT / "results" / "day4_observations.json")
    parser.add_argument("--day5", type=Path, default=ROOT / "results" / "day5_realworld.json")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    for p in (args.day4, args.day5, args.rules):
        if not p.is_file():
            parser.error(f"Required input not found: {p}. Complete Days 4 and 5 first.")
    data = run(args.day4, args.day5, args.rules, args.output)
    print("Day 6 state-invariant summary:", data["counts"])
    print("Disagreements with earlier targeted oracles:", data["disagreement_count"])
    print("Saved:", args.output / "day6_oracle_summary.md")


if __name__ == "__main__":
    main()
