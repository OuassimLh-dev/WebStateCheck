"""Day 15: source-pinned p-queue action executor *feasibility* study.

Does not seal target t01, does not generate AI tests, and does not score
hold-out bug detection. Compiles real pinned source and exercises public
operations to identify runnable, incomplete, and indeterminate sequences.

Commands:
  python -m webstatecheck.day15_executor prepare
  python -m webstatecheck.day15_executor smoke
  python -m webstatecheck.day15_executor matrix
"""
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, paths, sha, valid_public
from webstatecheck.day13_target import BEFORE, AFTER
from webstatecheck.day14_feasibility import analyze_sequence

TARGET = "t01"
SOURCE_DIR = Path("realworld/p_queue_holdout")
PROBE = SOURCE_DIR / "feasibility_runner.mjs"
REVISIONS = {"before": BEFORE, "after": AFTER}


def _run(args: list[str], *, cwd: Path, timeout: int = 240) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n"
                           f"stdout: {result.stdout[-1500:]}\nstderr: {result.stderr[-2500:]}")
    return result.stdout.strip()


def public_spec(root: Path = ROOT) -> dict:
    assert_day11_lock(root)
    stage, sealed = paths(root, TARGET)
    if sealed.exists():
        raise ValueError("t01 has been sealed; feasibility runner only accepts unsealed staging")
    specification = json.loads((stage / "public_spec.json").read_text(encoding="utf-8"))
    valid_public(specification, TARGET)
    return specification


def verify_prepared_source(root: Path = ROOT) -> Path:
    public = public_spec(root)
    repo = root / SOURCE_DIR / "upstream"
    record = root / "results" / "day13_source_verification.json"
    if not (repo / ".git").exists() or not record.is_file():
        raise ValueError("Run 'python -m webstatecheck.day13_target verify-source' first")
    verified = json.loads(record.read_text(encoding="utf-8"))
    if (verified.get("before_commit") != BEFORE or verified.get("after_commit") != AFTER
            or verified.get("public_spec_sha256") != sha(root / "research" / "holdout_staging" / TARGET / "public_spec.json")):
        raise ValueError("Source or public specification changed after Day 13 verification")
    # Public contract is also checked before use to avoid silently ignoring any redesign.
    if public["actions_per_scenario"] != 2 or public["scenarios_per_method"] != 4:
        raise ValueError("Unexpected budget; prepare a separate recorded amendment instead")
    return repo


def prepare(root: Path = ROOT) -> dict:
    repo = verify_prepared_source(root)
    artifacts = {}
    for label, commit in REVISIONS.items():
        target = root / SOURCE_DIR / "versions" / label
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            observed = _run(["git", "rev-parse", "HEAD"], cwd=target)
            if observed != commit:
                raise ValueError(f"Existing {label} worktree has wrong commit {observed}")
        else:
            _run(["git", "worktree", "add", "--detach", str(target), commit], cwd=repo, timeout=180)
        observed = _run(["git", "rev-parse", "HEAD"], cwd=target)
        if observed != commit:
            raise ValueError(f"Wrong source revision for {label}: {observed}")
        # The upstream manifest is never overwritten, and neither original nor pinned source is patched.
        if not (target / "dist" / "index.js").is_file():
            install_command = (["npm", "ci", "--no-audit", "--no-fund"]
                               if (target / "package-lock.json").exists()
                               else ["npm", "install", "--no-audit", "--no-fund", "--ignore-scripts"])
            _run(install_command, cwd=target, timeout=600)
            _run(["npm", "run", "build"], cwd=target, timeout=300)
        built = target / "dist" / "index.js"
        if not built.is_file():
            raise RuntimeError(f"Build did not produce {built}")
        artifacts[label] = {"commit": observed, "bundle": str(built), "sha256": sha(built)}
    result_dir = root / "results"
    result_dir.mkdir(exist_ok=True)
    output = {"evidence_level": "BUILD VERIFICATION, NOT AN AI OR DEFECT-DETECTION RESULT",
              "generated_utc": datetime.now(timezone.utc).isoformat(), "bundles": artifacts}
    (result_dir / "day15_build_provenance.json").write_text(canonical_json(output), encoding="utf-8")
    return output


def action_options(root: Path = ROOT) -> list[dict]:
    return [{"type": x["type"], "target": x["target"]} for x in public_spec(root)["allowed_actions"]]


def possible_scenarios(root: Path = ROOT) -> list[dict]:
    options = action_options(root)
    count = public_spec(root)["actions_per_scenario"]
    valid = []
    for index, combo in enumerate(itertools.product(options, repeat=count), 1):
        actions = list(combo)
        if analyze_sequence(actions)["executable_by_preconditions"]:
            valid.append({"plan_id": f"feasibility-{index:02d}", "actions": actions})
    return valid


def smoke_scenarios(root: Path = ROOT) -> list[dict]:
    # Generic public-contract probes only. No historical bug/patch details in this file.
    selected = [
        [("submit", "enqueue_quick_task"), ("click", "observe_idle_status")],
        [("submit", "enqueue_cancelable_task"), ("cancel", "current_signal")],
        [("submit", "enqueue_delayed_task"), ("click", "release_delayed_task")],
        [("submit", "enqueue_delayed_task"), ("click", "observe_idle_status")],
        [("submit", "enqueue_rejecting_task"), ("click", "observe_idle_status")],
        [("submit", "enqueue_quick_task"), ("submit", "enqueue_quick_task")],
    ]
    allowed = {(a["type"], a["target"]) for a in action_options(root)}
    scenarios = []
    for i, pairs in enumerate(selected, 1):
        assert all(pair in allowed for pair in pairs), "Public grammar changed; revise smoke scenarios"
        actions = [{"type": pair[0], "target": pair[1]} for pair in pairs]
        assert analyze_sequence(actions)["executable_by_preconditions"]
        scenarios.append({"plan_id": f"smoke-{i:02d}", "actions": actions})
    return scenarios


def evaluate(kind: str, root: Path = ROOT) -> dict:
    repo = verify_prepared_source(root)
    spec = public_spec(root)
    runner = root / PROBE
    if not runner.is_file():
        raise ValueError("Missing Node.js executor. Install the Day 15 add-on first")
    scenarios = smoke_scenarios(root) if kind == "smoke" else possible_scenarios(root)
    if not scenarios:
        raise RuntimeError("No feasible scenarios in current public grammar")
    records = []
    for label, commit in REVISIONS.items():
        target = root / SOURCE_DIR / "versions" / label
        if not (target / "dist" / "index.js").is_file():
            raise ValueError("Pinned source not built. Run 'python -m webstatecheck.day15_executor prepare'")
        if _run(["git", "rev-parse", "HEAD"], cwd=target) != commit:
            raise ValueError("Worktree is not pinned to the expected commit")
        payload = {"target_id": TARGET, "scenarios": scenarios,
                   "max_wait_ms": min(5000, spec["max_wait_ms_per_scenario"])}
        cmd = ["node", str(runner), str(target / "dist" / "index.js")]
        process = subprocess.run(cmd, input=canonical_json(payload), capture_output=True,
                                 text=True, cwd=repo, timeout=max(30, len(scenarios) * 6), check=False)
        if process.returncode:
            raise RuntimeError(f"Executor failed on {label}: {process.stderr[-2500:]}")
        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Executor emitted invalid JSON for {label}: {process.stdout[-600:]}") from exc
        if output.get("target_id") != TARGET or len(output.get("records", [])) != len(scenarios):
            raise RuntimeError(f"Unexpected output shape for {label}")
        for row in output["records"]:
            records.append({**row, "revision": label, "commit": commit})
    counts = {label: {
        "scenarios": sum(r["revision"] == label for r in records),
        "settled": sum(r["revision"] == label and r["status"] == "settled" for r in records),
        "needs_release": sum(r["revision"] == label and r["status"] == "needs_release" for r in records),
        "unresolved": sum(r["revision"] == label and r["status"] not in ("settled", "needs_release") for r in records),
        "capacity_violations": sum(r["revision"] == label and r["max_active"] > 1 for r in records),
    } for label in REVISIONS}
    output = {"evidence_level": "DEVELOPMENT FEASIBILITY ONLY — NOT BLINDED/AI/DISCOVERY",
              "generated_utc": datetime.now(timezone.utc).isoformat(), "kind": kind,
              "public_spec_sha256": sha(root / "research" / "holdout_staging" / TARGET / "public_spec.json"),
              "scenarios": scenarios, "summary": counts, "records": records}
    out = root / "results"
    out.mkdir(exist_ok=True)
    (out / f"day15_{kind}_observations.json").write_text(canonical_json(output), encoding="utf-8")
    report = [f"# Day 15 — p-queue {kind} feasibility", "", "**Not a held-out test and not an AI comparison.**",
              "", "Source: actual pinned upstream builds. Each scenario uses two actions and a fresh queue.",
              "Unreleased delayed tasks are observed as unfinished and then cleaned up.",
              "Task rejection is expected for rejecting/cancelled operations and is not automatically called a bug.",
              "", "| Revision | Scenarios | Settled | Needs release | Other unresolved | Concurrency violations |",
              "|---|---:|---:|---:|---:|---:|",]
    for label, info in counts.items():
        report.append(f"| {label} | {info['scenarios']} | {info['settled']} | {info['needs_release']} | {info['unresolved']} | {info['capacity_violations']} |")
    report.extend(["", "## Limitations", "",
                   "- An action 'observe_idle_status' consumes a scenario slot but is not a mutation; passive post-action snapshots are free for all methods.",
                   "- The two-action grammar cannot explore arbitrary three-step task/cancel/settle interleavings.",
                   "- An executor running a real library is not automatically a valid oracle for all documented behaviors.",
                   "- Source selection and this conversation have inspected the historical issue; this candidate is development/feasibility only.",
                   "- Frozen files and candidate registration remain unchanged; do not seal t01 from this report alone.", ""])
    (out / f"day15_{kind}_summary.md").write_text("\n".join(report), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "smoke", "matrix"))
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare()
            print("Built exact upstream source revisions:", list(result["bundles"]))
        else:
            output = evaluate(args.command)
            for label, entry in output["summary"].items():
                print(label, entry)
            print("Saved:", ROOT / "results" / f"day15_{args.command}_summary.md")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            json.JSONDecodeError, KeyError, TypeError) as exc:
        parser.exit(1, "Day 15: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
