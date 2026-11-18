"""Day 14: read-only pre-seal action-grammar feasibility audit for p-queue t01.

This checker analyzes action dependencies and potential unfinished tasks.
It does not execute JavaScript, access the bug/fix oracle, modify registrations,
seal the candidate, or make a holdout performance claim.

Usage:
    python -m webstatecheck.day14_feasibility audit
    python -m webstatecheck.day14_feasibility check --file my_plan.json
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, paths, valid_public

TARGET = "t01"


def analyze_sequence(actions: list[dict]) -> dict:
    """Conservative precondition analysis, not a JavaScript execution model.

    Any complete scenario can be inspected by the eventual oracle after its
    last action. For simplicity this audit does not simulate promise timing.
    """
    have_signal = False
    have_delayed = False
    cancelled = False
    errors: list[str] = []
    warnings: list[str] = []
    evidence = set()
    for position, action in enumerate(actions, start=1):
        pair = (action.get("type"), action.get("target"))
        if pair == ("submit", "enqueue_cancelable_task"):
            have_signal = True
            cancelled = False
            evidence.add("cancellation_setup")
        elif pair == ("submit", "enqueue_delayed_task"):
            have_delayed = True
            evidence.add("delayed_task")
        elif pair in {( "submit", "enqueue_quick_task"), ("submit", "enqueue_rejecting_task")}:
            evidence.add("settlement_candidate")
        elif pair == ("cancel", "current_signal"):
            if not have_signal:
                errors.append(f"action {position}: current_signal does not exist yet")
            elif cancelled:
                warnings.append(f"action {position}: signal already canceled")
            else:
                cancelled = True
                evidence.add("cancellation_action")
        elif pair == ("click", "release_delayed_task"):
            if not have_delayed:
                errors.append(f"action {position}: no delayed task has been queued")
            else:
                have_delayed = False
                evidence.add("delayed_release")
        elif pair == ("click", "observe_idle_status"):
            evidence.add("idle_observation")
            warnings.append(f"action {position}: observation consumes the same budget as a state-changing action")
        else:
            errors.append(f"action {position}: unsupported action {pair}")
    if have_delayed:
        warnings.append("scenario ends with an unreleased delayed task; the idle/settlement oracle may time out")
    if "cancellation_action" in evidence:
        evidence.add("cancellation_sequence")
    return {"executable_by_preconditions": not errors, "errors": errors,
            "warnings": warnings, "patterns": sorted(evidence)}


def audit(root: Path = ROOT) -> dict:
    """Read staged public packet only; do not inspect private truth."""
    lock_sha = assert_day11_lock(root)
    stage, sealed = paths(root, TARGET)
    if sealed.exists():
        raise ValueError("t01 has been sealed; pre-seal audit must not rewrite it")
    spec = json.loads((stage / "public_spec.json").read_text(encoding="utf-8"))
    valid_public(spec, TARGET)
    options = [{"type": a["type"], "target": a["target"]} for a in spec["allowed_actions"]]
    count = spec["actions_per_scenario"]
    samples = [analyze_sequence(list(sequence)) for sequence in itertools.product(options, repeat=count)]
    good = [record for record in samples if record["executable_by_preconditions"]]
    impossible = [record for record in samples if not record["executable_by_preconditions"]]
    unfinished = [record for record in good if any("unreleased delayed" in x for x in record["warnings"])]
    nonmutating = [record for record in good if any("observation consumes" in x for x in record["warnings"])]
    result = {
        "candidate": TARGET,
        "status": "NOT READY TO SEAL — public action semantics need review and runnable executor",
        "scope": "static public-grammar audit only; no target code executed",
        "day11_lock_sha256": lock_sha,
        "budget_actions_per_scenario": count,
        "allowed_actions": len(options),
        "enumerated_sequences": len(samples),
        "precondition_feasible_sequences": len(good),
        "sequences_with_invalid_preconditions": len(impossible),
        "feasible_sequences_with_unreleased_delayed_tasks": len(unfinished),
        "feasible_sequences_using_observation_as_budgeted_action": len(nonmutating),
        "requirements_before_sealing": [
            "Define exact before/after-state semantics for each action, including cancellation timing",
            "Define an automatic common post-action observation and stabilization policy",
            "Decide whether polling/observing counts toward the interaction budget",
            "Implement a source-pinned p-queue executor and test all supported sequences",
            "Revise nominal two-action budget via a separately recorded protocol if necessary",
            "Record leakage/contamination status; do not claim this conversation is blinded"
        ]
    }
    output = root / "results"
    output.mkdir(parents=True, exist_ok=True)
    (output / "day14_feasibility.json").write_text(canonical_json(result), encoding="utf-8")
    report = [
        "# Day 14 — Pre-seal action-grammar feasibility audit", "",
        "**Status: NOT READY TO SEAL.** No bug/fix execution or AI evaluation was performed.", "",
        f"Allowed action names: **{len(options)}**; actions per scenario: **{count}**.",
        f"All ordered two-action sequences: **{len(samples)}**.",
        f"Sequences passing the conservative precondition checker: **{len(good)}**.",
        f"Sequences rejected as impossible: **{len(impossible)}**.",
        f"Precondition-feasible sequences ending with an unreleased delayed task: **{len(unfinished)}**.",
        f"Precondition-feasible sequences using observation as a budgeted action: **{len(nonmutating)}**.", "",
        "This is a **syntactic/semantic precondition check**, not execution feasibility, race-detection coverage, or accuracy.", "",
        "## Required before sealing", ""
    ]
    report += [f"- {item}." for item in result["requirements_before_sealing"]]
    report += ["", "## Notes", "",
               "The checker reads only public_spec.json. The private issue, commits, and fix are not used in the audit.",
               "Do not modify the frozen nine-file manifest. Do not treat this candidate as a clean blinded comparison if the evaluator helped select it using bug knowledge.", ""]
    (output / "day14_feasibility.md").write_text("\n".join(report), encoding="utf-8")
    return result


def check_plan(path: Path, root: Path = ROOT) -> dict:
    assert_day11_lock(root)
    stage, _ = paths(root, TARGET)
    spec = json.loads((stage / "public_spec.json").read_text(encoding="utf-8"))
    valid_public(spec, TARGET)
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("target_id") != TARGET or not isinstance(plan.get("plans"), list):
        raise ValueError("wrong target or missing plans")
    allowed = {(a["type"], a["target"]) for a in spec["allowed_actions"]}
    checks = []
    for scenario in plan["plans"]:
        actions = scenario["actions"]
        if len(actions) != spec["actions_per_scenario"]:
            raise ValueError("wrong action budget in " + str(scenario.get("plan_id")))
        if any((a.get("type"), a.get("target")) not in allowed or set(a) != {"type", "target"} for a in actions):
            raise ValueError("action outside public grammar in " + str(scenario.get("plan_id")))
        checks.append({"plan_id": scenario["plan_id"], **analyze_sequence(actions)})
    return {"scenarios": len(checks), "precondition_valid": sum(x["executable_by_preconditions"] for x in checks),
            "details": checks, "note": "Preconditions only; no target JavaScript has executed"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit")
    sub.add_parser("check").add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.cmd == "audit":
            result = audit()
            print(f"Enumerated {result['enumerated_sequences']} action sequences; "
                  f"{result['precondition_feasible_sequences']} pass static preconditions; "
                  f"{result['sequences_with_invalid_preconditions']} impossible.")
            print(result["status"])
            print("Saved:", ROOT / "results/day14_feasibility.md")
        else:
            print(canonical_json(check_plan(args.file)))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, "Day 14 audit: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
