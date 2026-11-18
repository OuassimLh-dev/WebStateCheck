"""Day 17 — correct delayed-gate multiplicity and inspect full 3-action feasibility.

Commands:
  python -m webstatecheck.day17_gate_audit audit
  python -m webstatecheck.day17_gate_audit matrix --repeats 2

This is DEVELOPMENT ONLY on a known p-queue before/after case.
It neither modifies the frozen Day 11 files nor the staged t01 target.
It does not use private bug metadata or assert discovery/AI superiority.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, canonical_json, sha
from webstatecheck.day14_feasibility import analyze_sequence
from webstatecheck.day15_executor import (
    TARGET, PROBE, SOURCE_DIR, REVISIONS, _run, action_options,
    public_spec, verify_prepared_source,
)
from webstatecheck.day16_three_action import BUDGET_V2, enumerate_sequences

NOTICE = "DEVELOPMENT/FEASIBILITY ONLY; NOT BLINDED, AI, OR NEW DEFECT DISCOVERY"


def precise_preconditions(actions: list[dict]) -> dict:
    """Count every delayed gate, not just whether any gate ever existed.

    The model predicts unreleased gates as a *lower-level harness invariant*,
    not whether p-queue itself should be considered correct. It intentionally
    does not pretend to predict asynchronous scheduling or promise outcomes.
    """
    outstanding = 0
    signal_created = False
    signal_cancelled = False
    errors: list[str] = []
    warnings: list[str] = []
    patterns: set[str] = set()
    release_actions = 0
    submissions = 0
    observations = 0
    for index, action in enumerate(actions, 1):
        if not isinstance(action, dict) or set(action) != {"type", "target"}:
            errors.append(f"action {index}: must contain only type and target")
            continue
        key = (action["type"], action["target"])
        if key == ("submit", "enqueue_delayed_task"):
            outstanding += 1
            submissions += 1
            patterns.add("delayed_task")
        elif key == ("submit", "enqueue_cancelable_task"):
            signal_created = True
            signal_cancelled = False
            submissions += 1
            patterns.add("cancellation_setup")
        elif key in {("submit", "enqueue_quick_task"), ("submit", "enqueue_rejecting_task")}:
            submissions += 1
            patterns.add("settlement_candidate")
        elif key == ("cancel", "current_signal"):
            if not signal_created:
                errors.append(f"action {index}: no prior cancellable task/signal")
            elif signal_cancelled:
                warnings.append(f"action {index}: signal already cancelled (idempotent)")
            else:
                signal_cancelled = True
                patterns.add("cancellation_action")
        elif key == ("click", "release_delayed_task"):
            if outstanding == 0:
                errors.append(f"action {index}: no unreleased delayed gate")
            else:
                outstanding -= 1
                release_actions += 1
                patterns.add("delayed_release")
        elif key == ("click", "observe_idle_status"):
            observations += 1
            patterns.add("idle_observation")
            warnings.append(f"action {index}: an observation consumes an action slot")
        else:
            errors.append(f"action {index}: unsupported action {key}")
    if outstanding:
        warnings.append(f"{outstanding} delayed task gate(s) remain unreleased after final action")
    return {
        "executable_by_preconditions": not errors,
        "errors": errors,
        "warnings": warnings,
        "patterns": sorted(patterns),
        "unreleased_gates_predicted": outstanding,
        "release_actions": release_actions,
        "task_submissions": submissions,
        "observation_actions": observations,
        "post_action_state": "needs_release" if outstanding else "needs_runtime_check",
    }


def public_three_action_plans(options: list[dict]) -> tuple[list[dict], list[dict]]:
    """Enumerate public grammar, keep stable Day 16 IDs, no private truth."""
    rows = enumerate_sequences(options)
    decisions = [(row, precise_preconditions(row["actions"])) for row in rows]
    accepted = [
        {"plan_id": row["plan_id"], "actions": row["actions"], "predicted_unreleased_gates": prediction["unreleased_gates_predicted"]}
        for row, prediction in decisions if prediction["executable_by_preconditions"]
    ]
    return accepted, [
        {"plan_id": row["plan_id"], **prediction}
        for row, prediction in decisions
    ]


def validate_executed_row(row: dict) -> list[str]:
    """Check harness bookkeeping against the action plan (not bug truth)."""
    problems = []
    prediction = precise_preconditions(row["actions"])
    if not prediction["executable_by_preconditions"]:
        problems.append("executed a plan with invalid preconditions")
    if row.get("unreleased_gates") != prediction["unreleased_gates_predicted"]:
        problems.append(f"expected {prediction['unreleased_gates_predicted']} unreleased gates, "
                        f"observed {row.get('unreleased_gates')}")
    if row.get("status") not in {"settled", "needs_release", "unresolved"}:
        problems.append("unexpected status")
    elif prediction["unreleased_gates_predicted"] > 0 and row.get("status") != "needs_release":
        problems.append("unreleased gate not marked needs_release")
    elif prediction["unreleased_gates_predicted"] == 0 and row.get("status") == "needs_release":
        problems.append("needs_release without an unreleased gate")
    if not isinstance(row.get("outcomes"), list):
        problems.append("missing outcomes list")
    return problems


def normalized_observation(record: dict) -> dict:
    """Strip revision and timing; preserve observable outcomes (not just status).

    Exact errors/messages can vary legitimately across versions; differences
    are diagnostic leads, NOT automatic correctness violations.
    """
    out = []
    for item in record.get("outcomes", []):
        out.append({"id": item.get("id"), "type": item.get("type"),
                    "status": item.get("status"), "value": item.get("value"),
                    "error": item.get("error")})
    snapshot = record.get("queue_snapshot") or {}
    return {
        "status": record.get("status"),
        "unreleased_gates": record.get("unreleased_gates"),
        "pending_task_records": record.get("pending_task_records"),
        "outcomes": out,
        "queue_snapshot": {"pending": snapshot.get("pending"), "size": snapshot.get("size"),
                           "observed_idle": snapshot.get("observed_idle")},
        "max_active": record.get("max_active"),
        "events": record.get("events"),
    }


def compare_pair(before: dict, after: dict) -> list[str]:
    a, b = normalized_observation(before), normalized_observation(after)
    return [key for key in a if a[key] != b[key]]


def audit(root: Path = ROOT) -> dict:
    spec = public_spec(root)
    if spec["actions_per_scenario"] != 2 or spec["scenarios_per_method"] != 4:
        raise ValueError("t01 must remain staged with its original two-action registration")
    plans, rows = public_three_action_plans(action_options(root))
    original_disagreements = []
    old_warnings_missed = []
    old_by_id = {p["plan_id"]: p for p in enumerate_sequences(action_options(root))}
    for row in rows:
        old = analyze_sequence(old_by_id[row["plan_id"]]["actions"])
        if old["executable_by_preconditions"] != row["executable_by_preconditions"]:
            original_disagreements.append(row["plan_id"])
        had_old_pending_warning = any("unreleased delayed" in w for w in old["warnings"])
        if row["executable_by_preconditions"] and row["unreleased_gates_predicted"] > 0 and not had_old_pending_warning:
            old_warnings_missed.append(row["plan_id"])
    smoke_path = root / "results/day16_smoke_observations.json"
    smoke_issues = []
    smoke_checked = 0
    if smoke_path.is_file():
        saved = json.loads(smoke_path.read_text(encoding="utf-8"))
        for record in saved.get("records", []):
            smoke_checked += 1
            for issue in validate_executed_row(record):
                smoke_issues.append({"plan_id": record.get("plan_id"), "revision": record.get("revision"), "issue": issue})
    output = {
        "evidence_level": NOTICE,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": TARGET, "candidate_still_unsealed": True,
        "total_action_triples": len(rows), "precise_precondition_valid": len(plans),
        "precise_precondition_invalid": len(rows)-len(plans),
        "old_new_feasibility_disagreements": original_disagreements,
        "old_checker_missed_unreleased_gate_warnings": old_warnings_missed,
        "valid_with_one_or_more_pending_gates": sum(r["executable_by_preconditions"] and r["unreleased_gates_predicted"] > 0 for r in rows),
        "smoke_records_checked": smoke_checked,
        "smoke_bookkeeping_issues": smoke_issues,
        "day16_smoke_records_present": smoke_path.is_file(),
        "no_source_code_or_protocol_modified": True,
    }
    report = ["# Day 17 — Delayed-task bookkeeping audit", "",
              "**Development-only audit of the public three-action grammar. No historical issue detection or AI result.**", "",
              f"Enumerated sequences: **{len(rows)}**; precondition-valid: **{len(plans)}**; invalid: **{len(rows)-len(plans)}**.",
              f"Feasibility disagreements with Day 16: **{len(original_disagreements)}**.",
              f"Feasible sequences where the old Boolean checker missed an unreleased gate: **{len(old_warnings_missed)}**.",
              f"Valid sequences with outstanding gates under precise counting: **{output['valid_with_one_or_more_pending_gates']}**.",
              f"Saved Day 16 execution records checked: **{smoke_checked}**; infrastructure bookkeeping mismatches: **{len(smoke_issues)}**.", "",
              "The old checker tracked whether *any* delayed task existed, not the number of unreleased gates.",
              "This is a harness issue. Fixing its accounting does not show a defect in upstream p-queue.",
              "No Day 11 frozen files or staged t01 registrations have been modified.", "",
              "Next: run the full three-action matrix on the actual pinned upstream builds,", 
              "and inspect outcome-level differences separately from simple status counts.", ""]
    _save(root, "day17_gate_audit", output, report)
    return output


def _save(root: Path, name: str, body: dict, report: list[str]) -> None:
    directory = root / "results"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (name + ".json")).write_text(canonical_json(body), encoding="utf-8")
    (directory / (name + ".md")).write_text("\n".join(report), encoding="utf-8")


def matrix(root: Path = ROOT, *, repeats: int = 2) -> dict:
    if not 1 <= repeats <= 3:
        raise ValueError("repeats must be from 1 to 3")
    upstream = verify_prepared_source(root)
    spec = public_spec(root)
    if spec["actions_per_scenario"] != 2 or spec["scenarios_per_method"] != 4:
        raise ValueError("Staged original t01 registration unexpectedly modified")
    plans, _ = public_three_action_plans(action_options(root))
    probe = root / PROBE
    if not probe.is_file():
        raise ValueError("Day 15 executor missing; install the Day 15 add-on")
    provenance_path = root / "results/day15_build_provenance.json"
    if not provenance_path.is_file():
        raise ValueError("Day 15 source builds not prepared; run day15_executor prepare")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    bundles = {}
    for revision, commit in REVISIONS.items():
        checkout = root / SOURCE_DIR / "versions" / revision
        if _run(["git", "rev-parse", "HEAD"], cwd=checkout) != commit:
            raise ValueError(f"{revision} checkout does not match pinned upstream revision")
        bundle = checkout / "dist/index.js"
        pinned_hash = provenance.get("bundles", {}).get(revision, {}).get("sha256")
        if not bundle.is_file() or not pinned_hash or sha(bundle) != pinned_hash:
            raise ValueError(f"{revision} bundle missing or hash does not match Day 15 provenance")
        bundles[revision] = {"path": str(bundle), "sha256": pinned_hash, "commit": commit}
    expected = {p["plan_id"]: p["actions"] for p in plans}
    observations = []
    for trial in range(1, repeats + 1):
        for revision in REVISIONS:
            payload = {"target_id": TARGET,
                       "scenarios": [{"plan_id": p["plan_id"], "actions": p["actions"]} for p in plans],
                       "max_wait_ms": min(5000, spec["max_wait_ms_per_scenario"])}
            cmd = ["node", str(probe), bundles[revision]["path"]]
            proc = subprocess.run(cmd, input=canonical_json(payload), capture_output=True,
                                  text=True, cwd=upstream, timeout=max(120, len(plans)*2), check=False)
            if proc.returncode:
                raise RuntimeError(f"Node executor failed, {revision} trial {trial}: {proc.stderr[-1600:]}")
            try:
                result = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Node executor produced invalid JSON") from exc
            records = result.get("records")
            if result.get("target_id") != TARGET or not isinstance(records, list) or len(records) != len(plans):
                raise RuntimeError("Node result count or target ID mismatch")
            ids = [r.get("plan_id") for r in records]
            if len(set(ids)) != len(plans) or set(ids) != set(expected):
                raise RuntimeError("Node result scenarios differ from the planned matrix")
            for record in records:
                if record.get("actions") != expected[record["plan_id"]]:
                    raise RuntimeError("Executor returned changed actions")
                observations.append({"revision": revision, "repeat": trial, **record})
    index = {(r["repeat"], r["revision"], r["plan_id"]): r for r in observations}
    diff = []
    infrastructure_issues = []
    for record in observations:
        for issue in validate_executed_row(record):
            infrastructure_issues.append({"repeat": record["repeat"], "revision": record["revision"],
                                          "plan_id": record["plan_id"], "issue": issue})
    for trial in range(1, repeats+1):
        for plan in plans:
            pid = plan["plan_id"]
            changed = compare_pair(index[(trial, "before", pid)], index[(trial, "after", pid)])
            if changed:
                diff.append({"repeat": trial, "plan_id": pid, "changed_observables": changed})
    unstable = []
    if repeats > 1:
        for revision in REVISIONS:
            for plan in plans:
                pid = plan["plan_id"]
                snapshots = [normalized_observation(index[(trial, revision, pid)]) for trial in range(1, repeats+1)]
                if any(s != snapshots[0] for s in snapshots[1:]):
                    unstable.append({"revision": revision, "plan_id": pid})
    counts = {}
    for revision in REVISIONS:
        subset = [r for r in observations if r["revision"] == revision]
        c = Counter(r.get("status") for r in subset)
        counts[revision] = {"executions": len(subset), "settled": c["settled"],
                            "needs_release": c["needs_release"], "unresolved": c["unresolved"],
                            "capacity_over_one": sum(r.get("max_active", 0) > 1 for r in subset),
                            "unreleased_gates_total": sum(r["unreleased_gates"] for r in subset)}
    result = {
        "evidence_level": NOTICE, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": TARGET, "candidate_still_unsealed": True,
        "plans_per_revision_per_repeat": len(plans), "actions_per_plan": BUDGET_V2,
        "repeats": repeats, "total_executions": len(observations),
        "public_spec_sha256": sha(root / "research/holdout_staging/t01/public_spec.json"),
        "bundle_provenance": bundles, "counts": counts,
        "cross_revision_observation_differences": diff,
        "repeat_instability": unstable,
        "harness_bookkeeping_mismatches": infrastructure_issues,
        "observations": observations,
    }
    report = ["# Day 17 — Full three-action matrix (development only)", "",
              "**Actual pinned upstream p-queue modules. NOT a held-out benchmark, AI comparison, or confirmed defect list.**", "",
              f"Three-action plans per revision per repeat: **{len(plans)}**; repeats: **{repeats}**.",
              f"Total executions: **{len(observations)}**. Frozen Day 11 files and staged t01 packet unchanged.", "",
              "| Revision | Executions | Settled | Needs release | Unresolved | Concurrency >1 |",
              "|---|---:|---:|---:|---:|---:|"]
    for label in REVISIONS:
        c = counts[label]
        report.append(f"| {label} | {c['executions']} | {c['settled']} | {c['needs_release']} | {c['unresolved']} | {c['capacity_over_one']} |")
    report += ["", f"Revision-paired executions with *any* observed-field difference: **{len(diff)}**.",
               f"Scenario/revision combinations that differed across repeats: **{len(unstable)}**.",
               f"Harness bookkeeping mismatches: **{len(infrastructure_issues)}**.", "",
               "Differences include task outcomes, event logs, snapshots and status; they are NOT automatically bugs.",
               "Stable agreement also does NOT prove correctness. Hand-authored oracles remain to be validated independently.",
               "An exhaustive matrix is a diagnostic study, not an equal-budget comparison of random vs heuristic vs AI.", "",
               "## First observed differences (diagnostic leads only)", ""]
    if diff:
        for item in diff[:12]:
            report.append(f"- Repeat {item['repeat']} · `{item['plan_id']}`: {', '.join(item['changed_observables'])}")
    else:
        report.append("No observable before/after differences detected in this matrix under this runner.")
    if infrastructure_issues:
        report.extend(["", "## Infrastructure mismatch examples", ""])
        for item in infrastructure_issues[:12]:
            report.append(f"- Repeat {item['repeat']} · {item['revision']} · `{item['plan_id']}`: {item['issue']}")
    report.extend(["", "**Do not seal t01.** This conversation already knows the historical source/fix; a new isolated target and protocol amendment are necessary for future independent evaluation.", ""])
    _save(root, "day17_matrix_summary", result, report)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit")
    matrix_parser = sub.add_parser("matrix")
    matrix_parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    try:
        if args.cmd == "audit":
            result = audit()
            print(f"Precise feasibility: {result['precise_precondition_valid']} valid of {result['total_action_triples']}")
            print(f"Old checker missed {len(result['old_checker_missed_unreleased_gate_warnings'])} unreleased-gate warnings")
            print(f"Day 16 smoke records checked: {result['smoke_records_checked']}; bookkeeping mismatches: {len(result['smoke_bookkeeping_issues'])}")
            print("Saved:", ROOT / "results/day17_gate_audit.md")
        else:
            result = matrix(repeats=args.repeats)
            print("Executed:", result["total_executions"], "over", args.repeats, "repeats")
            print("Counts:", result["counts"])
            print("Cross-revision observational differences:", len(result["cross_revision_observation_differences"]))
            print("Within-revision repeat instability:", len(result["repeat_instability"]))
            print("Harness bookkeeping mismatches:", len(result["harness_bookkeeping_mismatches"]))
            print("Saved:", ROOT / "results/day17_matrix_summary.md")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, TypeError) as exc:
        parser.exit(1, "Day 17: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
