"""Day 12: independent holdout registration / provenance tools.

Does not select a defect, run a model, or claim an evaluation result.
Does not modify Day 11's nine frozen files.

Commands:
  python -m webstatecheck.day12_holdout preflight
  python -m webstatecheck.day12_holdout scaffold --id t01
  python -m webstatecheck.day12_holdout seal --id t01
  python -m webstatecheck.day12_holdout verify --id t01
  python -m webstatecheck.day12_holdout validate-plan --id t01 --file PATH --method random
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webstatecheck.day11_audit import verify as verify_day11

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
METHODS = ("random", "heuristic", "llm")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def safe_id(value: str) -> str:
    if not ID.fullmatch(value):
        raise ValueError("Target ID must be 2–32 lowercase characters, digits, '_' or '-', starting with a letter")
    return value


def paths(root: Path, target_id: str) -> tuple[Path, Path]:
    safe_id(target_id)
    base = root / "research" / "holdout_staging" / target_id
    sealed = root / "research" / "holdout_sealed" / target_id
    return base, sealed


def assert_day11_lock(root: Path) -> str:
    lock = root / "research/day11_future_protocol_lock.json"
    if not lock.is_file():
        raise ValueError("Day 11 protocol lock missing. Run day11_audit freeze in your main project first.")
    drift = verify_day11(root)
    if drift:
        raise ValueError("Frozen Day 11 files changed: " + ", ".join(drift))
    return sha(lock)


def preflight(root: Path = ROOT) -> dict:
    lock_hash = assert_day11_lock(root)
    versions = {"python": sys.version.split()[0], "platform": platform.platform()}
    for name in ("git", "node", "npm"):
        try:
            output = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=8, check=True)
            versions[name] = output.stdout.strip() or output.stderr.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            versions[name] = "unavailable"
    try:
        from importlib.metadata import version
        versions["playwright"] = version("playwright")
        versions["pytest"] = version("pytest")
    except Exception:
        versions["playwright"] = "unknown"
        versions["pytest"] = "unknown"
    payload = {"status": "PREFLIGHT ONLY — no holdouts selected or evaluated",
               "recorded_utc": datetime.now(timezone.utc).isoformat(),
               "day11_lock_sha256": lock_hash, "environment": versions}
    out = root / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "day12_preflight.json").write_text(canonical_json(payload), encoding="utf-8")
    report = ["# Day 12 — Held-out study preflight", "",
              "**No independent target registered, no AI plan executed, no bug discovery claimed.**", "",
              f"Day 11 frozen manifest verified. SHA-256: `{lock_hash}`", "",
              "## Recorded environment", ""]
    report += [f"- {key}: `{value}`" for key, value in sorted(versions.items())]
    report += ["", "Next: select a NEW independent project, derive a behavior contract without leaking historical defect details, then register and seal its target packet.", ""]
    (out / "day12_preflight.md").write_text("\n".join(report), encoding="utf-8")
    return payload


def scaffold(root: Path, target_id: str) -> tuple[Path, Path]:
    assert_day11_lock(root)
    base, sealed = paths(root, target_id)
    if base.exists() or sealed.exists():
        raise FileExistsError(f"Target {target_id} already registered/staged: never silently overwrite")
    base.mkdir(parents=True)
    public = {
        "target_id": target_id,
        "interface_description": "FILL FROM PUBLIC API / USER-FACING CONTRACT ONLY",
        "allowed_actions": [
            {"type": "input", "target": "FILL_TARGET", "values": ["FILL_VALUE_1", "FILL_VALUE_2"]},
            {"type": "click", "target": "FILL_TARGET"}
        ],
        "observable_contracts": [{"name": "FILL_NAME", "description": "FILL_EXPECTED_BEHAVIOR"}],
        "reset_strategy": "FILL_REPRODUCIBLE_RESET",
        "scenarios_per_method": 4, "actions_per_scenario": 2,
        "max_wait_ms_per_scenario": 5000
    }
    private = {
        "target_id": target_id,
        "project_url": "https://github.com/OWNER/REPOSITORY",
        "before_commit": "FILL_FULL_40_CHAR_HASH",
        "after_commit": "FILL_FULL_40_CHAR_HASH",
        "issue_url": "FILL_IN_PRIVATE_ONLY",
        "bug_description": "FILL_IN_PRIVATE_ONLY",
        "license": "VERIFY_UPSTREAM_LICENSE",
        "environment_notes": "FILL_BUILD_AND_PERMISSION_NOTES"
    }
    (base / "public_spec.json").write_text(canonical_json(public), encoding="utf-8")
    (base / "PRIVATE_truth.json").write_text(canonical_json(private), encoding="utf-8")
    (base / "README.txt").write_text(
        "DRAFT ONLY. Fill public_spec.json using general public behavior, not hidden issue details.\n"
        "Keep PRIVATE_truth.json away from the test generator, and do not paste it into the LLM prompt.\n"
        "Only seal after checking source commits, license, contracts, and per-target budgets.\n",
        encoding="utf-8")
    return base / "public_spec.json", base / "PRIVATE_truth.json"


def valid_public(spec: Any, target_id: str) -> None:
    if not isinstance(spec, dict) or set(spec) != {
        "target_id", "interface_description", "allowed_actions", "observable_contracts",
        "reset_strategy", "scenarios_per_method", "actions_per_scenario", "max_wait_ms_per_scenario"}:
        raise ValueError("Public spec keys do not match the registered schema")
    if spec["target_id"] != target_id:
        raise ValueError("Target ID mismatch in public specification")
    for key in ("interface_description", "reset_strategy"):
        if not isinstance(spec[key], str) or len(spec[key].strip()) < 20 or "FILL" in spec[key]:
            raise ValueError(f"Complete public {key} before sealing")
    if spec["scenarios_per_method"] != 4 or spec["actions_per_scenario"] != 2:
        raise ValueError("Frozen nominal budget is 4 scenarios × 2 actions. New budgets require a separately registered protocol revision.")
    if type(spec["max_wait_ms_per_scenario"]) is not int or not 500 <= spec["max_wait_ms_per_scenario"] <= 30000:
        raise ValueError("Explicit wait budget required (500–30000 ms)")
    actions = spec["allowed_actions"]
    if not isinstance(actions, list) or not actions:
        raise ValueError("Register at least one allowed action")
    seen = set()
    for action in actions:
        if not isinstance(action, dict) or set(action) not in ({"type", "target"}, {"type", "target", "values"}):
            raise ValueError("Allowed action must have type, target, optional values")
        typ, target = action["type"], action["target"]
        if typ not in {"click", "input", "submit", "cancel", "select"} or not isinstance(target, str) or not target or "FILL" in target:
            raise ValueError("Invalid/unfilled action type or target")
        if (typ, target) in seen:
            raise ValueError("Duplicate action type/target")
        seen.add((typ, target))
        if "values" in action and (not isinstance(action["values"], list) or not action["values"]
                                    or not all(isinstance(x, str) and x and "FILL" not in x for x in action["values"])):
            raise ValueError("Allowed values must be filled nonempty strings")
        if typ in {"input", "select"} and "values" not in action:
            raise ValueError("Input/select actions require allowed values")
        if typ not in {"input", "select"} and "values" in action:
            raise ValueError("Only input/select actions use values")
    obs = spec["observable_contracts"]
    if not isinstance(obs, list) or not obs or not all(isinstance(x, dict) and set(x) == {"name", "description"}
             and all(isinstance(v, str) and v.strip() and "FILL" not in v for v in x.values()) for x in obs):
        raise ValueError("At least one complete observable behavior contract is required")
    # Not a complete leakage detector: human inspection is still mandatory.
    text_blob = json.dumps(spec).lower()
    for phrase in ("fix commit", "bug #", "pull request #", "regression test for", "known vulnerability"):
        if phrase in text_blob:
            raise ValueError("Possible hidden-issue leakage in public specification")


def valid_private(spec: Any, target_id: str) -> None:
    if not isinstance(spec, dict) or set(spec) != {
        "target_id", "project_url", "before_commit", "after_commit", "issue_url",
        "bug_description", "license", "environment_notes"}:
        raise ValueError("Private truth schema mismatch")
    if spec["target_id"] != target_id:
        raise ValueError("Target ID mismatch in private specification")
    if not isinstance(spec["project_url"], str) or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", spec["project_url"]):
        raise ValueError("Project URL must identify a GitHub repository")
    if any(not isinstance(spec[k], str) or not HEX40.fullmatch(spec[k]) for k in ("before_commit", "after_commit")):
        raise ValueError("Use two full 40-character lowercase Git commits")
    if spec["before_commit"] == spec["after_commit"]:
        raise ValueError("Before/after commits must differ")
    for key in ("issue_url", "bug_description", "license", "environment_notes"):
        if not isinstance(spec[key], str) or len(spec[key].strip()) < 8 or "FILL" in spec[key] or "VERIFY" in spec[key]:
            raise ValueError(f"Complete private {key} before sealing")


def seal(root: Path, target_id: str) -> dict:
    lock_hash = assert_day11_lock(root)
    staged, sealed = paths(root, target_id)
    if sealed.exists():
        raise FileExistsError("Target already sealed. Do not change it after seeing results.")
    public_path, private_path = staged / "public_spec.json", staged / "PRIVATE_truth.json"
    public = json.loads(public_path.read_text(encoding="utf-8"))
    private = json.loads(private_path.read_text(encoding="utf-8"))
    valid_public(public, target_id)
    valid_private(private, target_id)
    # The model-facing packet intentionally removes all source-URL and defect metadata.
    packet = {"study": "WebStateCheck prospective evaluation", "target_id": target_id,
              "interface_description": public["interface_description"],
              "allowed_actions": public["allowed_actions"],
              "observable_contracts": public["observable_contracts"],
              "budget": {"scenarios": 4, "actions_per_scenario": 2,
                         "max_wait_ms_per_scenario": public["max_wait_ms_per_scenario"]},
              "instructions": "Generate test actions only. Do not infer bug labels or verdicts. No external browsing."}
    sealed.mkdir(parents=True)
    public_bytes, private_bytes = public_path.read_bytes(), private_path.read_bytes()
    (sealed / "public_spec.json").write_bytes(public_bytes)
    (sealed / "PRIVATE_truth.json").write_bytes(private_bytes)
    (sealed / "generator_packet.json").write_text(canonical_json(packet), encoding="utf-8")
    hashes = {name: sha(sealed / name) for name in ("public_spec.json", "PRIVATE_truth.json", "generator_packet.json")}
    manifest = {"target_id": target_id, "sealed_utc": datetime.now(timezone.utc).isoformat(),
                "day11_lock_sha256": lock_hash, "file_sha256": hashes,
                "status": "REGISTERED ONLY — source commit relation not independently verified; no AI generation or evaluation performed"}
    (sealed / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    return manifest


def verify(root: Path, target_id: str) -> dict:
    lock_hash = assert_day11_lock(root)
    _, sealed = paths(root, target_id)
    m = json.loads((sealed / "manifest.json").read_text(encoding="utf-8"))
    if m["day11_lock_sha256"] != lock_hash or m["target_id"] != target_id:
        raise ValueError("Frozen protocol identity/target identity mismatch")
    for name, expected in m["file_sha256"].items():
        if name not in {"public_spec.json", "PRIVATE_truth.json", "generator_packet.json"} or sha(sealed / name) != expected:
            raise ValueError("Sealed target changed: " + name)
    return m


def validate_plan(root: Path, target_id: str, path: Path, method: str) -> dict:
    verify(root, target_id)
    if method not in METHODS:
        raise ValueError("Choose random, heuristic or llm")
    _, sealed = paths(root, target_id)
    packet = json.loads((sealed / "generator_packet.json").read_text(encoding="utf-8"))
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or set(plan) != {"target_id", "method", "generator", "plans"}:
        raise ValueError("Plan must have target_id, method, generator, plans")
    if plan["target_id"] != target_id or plan["method"] != method:
        raise ValueError("Plan target or method mismatch")
    gen = plan["generator"]
    if not isinstance(gen, dict) or not all(isinstance(gen.get(k), str) and gen[k].strip() for k in ("name", "recorded_utc")):
        raise ValueError("Generator name and UTC timestamp are required")
    if method == "llm" and not all(isinstance(gen.get(k), str) and gen[k].strip() for k in ("model", "prompt_sha256", "raw_response_sha256")):
        raise ValueError("LLM plans require model, prompt hash, and raw model-response hash")
    options = {(x["type"], x["target"]): x for x in packet["allowed_actions"]}
    plans = plan["plans"]
    if not isinstance(plans, list) or len(plans) != 4:
        raise ValueError("Exactly four test scenarios required")
    ids = set()
    for scenario in plans:
        if not isinstance(scenario, dict) or set(scenario) != {"plan_id", "actions"}:
            raise ValueError("Each scenario needs only plan_id and actions")
        pid = scenario["plan_id"]
        if not isinstance(pid, str) or not pid or pid in ids:
            raise ValueError("Missing/duplicate plan ID")
        ids.add(pid)
        acts = scenario["actions"]
        if not isinstance(acts, list) or len(acts) != 2:
            raise ValueError("Exactly 2 actions per scenario")
        for a in acts:
            if not isinstance(a, dict) or set(a) not in ({"type", "target"}, {"type", "target", "value"}):
                raise ValueError("Each action needs type, target, optional value")
            conf = options.get((a["type"], a["target"]))
            if conf is None:
                raise ValueError("Action outside permitted interface grammar")
            if "values" in conf and a.get("value") not in conf["values"]:
                raise ValueError("Action uses unsupported input value")
            if "values" not in conf and "value" in a:
                raise ValueError("Action has unexpected value")
    return {"target_id": target_id, "method": method, "scenarios": 4, "actions": 8,
            "candidate_sha256": sha(path), "status": "PLAN VALIDATED ONLY — NOT EXECUTED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    for cmd in ("scaffold", "seal", "verify"):
        sub.add_parser(cmd).add_argument("--id", required=True)
    valid = sub.add_parser("validate-plan")
    valid.add_argument("--id", required=True)
    valid.add_argument("--method", choices=METHODS, required=True)
    valid.add_argument("--file", type=Path, required=True)
    opts = parser.parse_args()
    try:
        if opts.command == "preflight":
            info = preflight()
            print("Day 11 lock verified; environment recorded.")
            print("Saved:", ROOT / "results/day12_preflight.md")
            print("Held-out targets registered: none by this command.")
        elif opts.command == "scaffold":
            a, b = scaffold(ROOT, opts.id)
            print("Staged PUBLIC spec:", a)
            print("Staged PRIVATE truth (DO NOT GIVE TO GENERATOR):", b)
            print("No target sealed or evaluated.")
        elif opts.command == "seal":
            print(json.dumps(seal(ROOT, opts.id), indent=2))
        elif opts.command == "verify":
            print("Sealed target verified:", verify(ROOT, opts.id)["target_id"])
        else:
            print(json.dumps(validate_plan(ROOT, opts.id, opts.file, opts.method), indent=2))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Day 12: {exc}\n")


if __name__ == "__main__":
    main()
