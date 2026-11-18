"""Day 13: select/stage and source-verify an independent evaluation candidate.

No model generation, trial execution, or holdout performance claims.
Does not alter the Day 11 frozen files.

Run:
  python -m webstatecheck.day13_target prepare
  python -m webstatecheck.day13_target verify-source
  python -m webstatecheck.day13_target show-public
  python -m webstatecheck.day13_target seal --public-reviewed
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day12_holdout import (
    ROOT, assert_day11_lock, canonical_json, paths, scaffold, seal, sha, valid_public, valid_private, verify
)

TARGET = "t01"
REPO = "https://github.com/sindresorhus/p-queue"
BEFORE = "de565c42a271bd3c2f8c69d3b6bce33f49f9d344"
AFTER = "507e7eeab74970b991f1335b3f08cb5e08207ca3"
ISSUE = "https://github.com/sindresorhus/p-queue/issues/256"

PUBLIC = {
    "target_id": TARGET,
    "interface_description": (
        "A JavaScript promise queue schedules asynchronous tasks with configurable "
        "concurrency and supports canceling queued or running tasks using AbortSignal. "
        "The interface exposes task outcomes and queue idle status."
    ),
    "allowed_actions": [
        {"type": "submit", "target": "enqueue_quick_task"},
        {"type": "submit", "target": "enqueue_delayed_task"},
        {"type": "submit", "target": "enqueue_rejecting_task"},
        {"type": "submit", "target": "enqueue_cancelable_task"},
        {"type": "cancel", "target": "current_signal"},
        {"type": "click", "target": "release_delayed_task"},
        {"type": "click", "target": "observe_idle_status"}
    ],
    "observable_contracts": [
        {"name": "settlement", "description": "A completed task exposes a fulfilled or rejected result."},
        {"name": "cancellation", "description": "A task canceled through its signal follows the documented cancellation contract."},
        {"name": "capacity", "description": "A single-concurrency queue must not execute two tasks simultaneously."},
        {"name": "idle", "description": "Once all scheduled tasks have settled, a queue can become idle."}
    ],
    "reset_strategy": "Construct a fresh in-memory queue and fresh abort controllers for each scenario; do not share tasks across trials.",
    "scenarios_per_method": 4,
    "actions_per_scenario": 2,
    "max_wait_ms_per_scenario": 5000,
}

PRIVATE = {
    "target_id": TARGET,
    "project_url": REPO,
    "before_commit": BEFORE,
    "after_commit": AFTER,
    "issue_url": ISSUE,
    "bug_description": "Recorded privately: missed cancellation notification when a task aborts its own signal during initial execution. This text MUST NOT enter a model prompt.",
    "license": "MIT (package.json at both pinned revisions)",
    "environment_notes": (
        "Node.js >=20; upstream native ESM TypeScript project; clone pinned commits, "
        "install dependencies from npm, and build with npm run build in an isolated directory. "
        "Action-grammar feasibility and executor mapping require prospective review."
    ),
}


def prepare(root: Path = ROOT) -> tuple[Path, Path]:
    assert_day11_lock(root)
    public_path, private_path = scaffold(root, TARGET)
    valid_public(PUBLIC, TARGET)
    valid_private(PRIVATE, TARGET)
    public_path.write_text(canonical_json(PUBLIC), encoding="utf-8")
    private_path.write_text(canonical_json(PRIVATE), encoding="utf-8")
    return public_path, private_path


def _git(*args: str, cwd: Path | None = None, timeout: int = 120) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, check=True)
    return proc.stdout.strip()


def verify_source(root: Path = ROOT) -> dict:
    assert_day11_lock(root)
    staged, sealed = paths(root, TARGET)
    if sealed.exists():
        raise ValueError("Already sealed; use day12_holdout verify, do not re-register")
    public = json.loads((staged / "public_spec.json").read_text(encoding="utf-8"))
    private = json.loads((staged / "PRIVATE_truth.json").read_text(encoding="utf-8"))
    valid_public(public, TARGET)
    valid_private(private, TARGET)
    if private["project_url"] != REPO or private["before_commit"] != BEFORE or private["after_commit"] != AFTER:
        raise ValueError("Target source metadata drifted; manual review required")
    repo = root / "realworld" / "p_queue_holdout" / "upstream"
    repo.parent.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        if repo.exists():
            raise ValueError("Non-Git source directory exists, refusing overwrite: " + str(repo))
        _git("clone", "--filter=blob:none", "--no-checkout", REPO + ".git", str(repo), timeout=180)
    for commit in (BEFORE, AFTER):
        try:
            _git("cat-file", "-e", f"{commit}^{{commit}}", cwd=repo, timeout=30)
        except subprocess.CalledProcessError:
            _git("fetch", "origin", commit, cwd=repo, timeout=180)
        got = _git("rev-parse", f"{commit}^{{commit}}", cwd=repo)
        if got != commit:
            raise ValueError("Commit identity not verified: " + commit)
    direct_parent = _git("rev-parse", AFTER + "^", cwd=repo)
    if direct_parent != BEFORE:
        raise ValueError("Unexpected relationship: before is not direct parent of fix")
    licenses = {}
    for label, commit in (("before", BEFORE), ("after", AFTER)):
        package = json.loads(_git("show", f"{commit}:package.json", cwd=repo))
        licenses[label] = package.get("license")
        if licenses[label] != "MIT":
            raise ValueError("Unverified license at " + commit)
        _git("cat-file", "-e", f"{commit}:source/index.ts", cwd=repo)
    out = {
        "target_id": TARGET,
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SOURCE-VERIFIED CANDIDATE ONLY: no holdout tests or AI plans run",
        "before_commit": BEFORE,
        "after_commit": AFTER,
        "parent_relation": "direct parent",
        "licenses": licenses,
        "public_spec_sha256": sha(staged / "public_spec.json"),
        "private_truth_sha256": sha(staged / "PRIVATE_truth.json"),
        "note": "Candidate still requires manual contract review and a working equal-budget executor."
    }
    results = root / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "day13_source_verification.json").write_text(canonical_json(out), encoding="utf-8")
    return out


def seal_reviewed(root: Path = ROOT, public_reviewed: bool = False) -> dict:
    if not public_reviewed:
        raise ValueError("Require explicit --public-reviewed after checking action feasibility and no leakage")
    verified_path = root / "results/day13_source_verification.json"
    checked = json.loads(verified_path.read_text(encoding="utf-8"))
    staged, _ = paths(root, TARGET)
    if checked["public_spec_sha256"] != sha(staged / "public_spec.json") or checked["private_truth_sha256"] != sha(staged / "PRIVATE_truth.json"):
        raise ValueError("Staged registration changed after source verification")
    if checked["before_commit"] != BEFORE or checked["after_commit"] != AFTER:
        raise ValueError("Source identity mismatch")
    return seal(root, TARGET)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("prepare", "verify-source", "show-public", "status"):
        sub.add_parser(cmd)
    sub.add_parser("seal").add_argument("--public-reviewed", action="store_true")
    opts = parser.parse_args()
    try:
        if opts.command == "prepare":
            public, private = prepare()
            print("Candidate staged, not sealed:", public)
            print("Private evaluation metadata stored separately:", private)
        elif opts.command == "verify-source":
            data = verify_source()
            print("Verified pinned upstream revisions and MIT licenses.")
            print("Before:", data["before_commit"])
            print("After: ", data["after_commit"])
            print("No AI generation or experiments executed.")
            print("Saved:", ROOT / "results/day13_source_verification.json")
        elif opts.command == "show-public":
            staged, _ = paths(ROOT, TARGET)
            print((staged / "public_spec.json").read_text(encoding="utf-8"))
            print("Review public API grammar and execution feasibility BEFORE sealing.")
        elif opts.command == "status":
            staged, sealed_path = paths(ROOT, TARGET)
            print(json.dumps({"staged": staged.exists(), "sealed": sealed_path.exists(),
                              "source_verified_report": (ROOT / "results/day13_source_verification.json").exists()}, indent=2))
        else:
            print(json.dumps(seal_reviewed(public_reviewed=opts.public_reviewed), indent=2))
            print("Registered only. No held-out evaluation is claimed.")
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError) as exc:
        parser.exit(1, "Day 13: " + str(exc) + "\n")

if __name__ == "__main__":
    main()
