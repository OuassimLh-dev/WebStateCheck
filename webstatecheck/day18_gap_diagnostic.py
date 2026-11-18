"""Day 18: explain an observed p-queue action-grammar coverage gap using a
KNOWN historical issue and source-pinned diagnostic controls.

Development-only. This explicitly does not modify frozen Day 11 files, staged
candidate t01, or source revisions, and never claims a blind AI experiment.

Run:
  python -m webstatecheck.day18_gap_diagnostic run --repeats 3
  python -m webstatecheck.day18_gap_diagnostic report
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha
from webstatecheck.day15_executor import SOURCE_DIR, REVISIONS, verify_prepared_source

CASE_IDS = (
    "sync_self_abort", "microtask_self_abort", "external_abort", "no_abort_control"
)
NOTE = "Known-bug targeted diagnostic, NOT blinded, AI-generated, or new defect discovery"
PROBE = SOURCE_DIR / "day18_abort_probe.mjs"
OUTPUT_JSON = "day18_gap_observations.json"
OUTPUT_MD = "day18_gap_summary.md"


def get_source_bundles(root: Path) -> dict[str, Path]:
    """Check build identities rather than trusting labels or modifying either build."""
    verify_prepared_source(root)
    provenance_file = root / "results/day15_build_provenance.json"
    if not provenance_file.is_file():
        raise ValueError("Missing Day 15 build record; run day15_executor prepare")
    provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
    bundles = {}
    for label, commit in REVISIONS.items():
        folder = root / SOURCE_DIR / "versions" / label
        bundle = folder / "dist/index.js"
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=folder, text=True,
                              capture_output=True, timeout=30, check=True)
        if proc.stdout.strip() != commit:
            raise ValueError(f"Wrong checked-out source in {label} worktree")
        expected = provenance["bundles"].get(label)
        if not expected or expected["commit"] != commit or not bundle.is_file():
            raise ValueError("Missing or mismatched pinned build. Rerun day15_executor prepare")
        if sha(bundle) != expected["sha256"]:
            raise ValueError(f"Built JS changed since Day 15: {label}; do not proceed")
        bundles[label] = bundle
    return bundles


def invoke_node(runner: Path, bundle: Path, observe_ms: int) -> list[dict]:
    if not runner.is_file():
        raise ValueError("Missing Day 18 Node probe; reinstall add-on")
    request = {"case_ids": CASE_IDS, "observe_ms": observe_ms}
    proc = subprocess.run(["node", str(runner), str(bundle)],
                          input=canonical_json(request), text=True, capture_output=True,
                          timeout=35, check=False)
    if proc.returncode:
        raise RuntimeError(f"Node diagnostic failed: {proc.stderr[-2000:]}")
    try:
        output = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Node diagnostic did not return JSON") from exc
    cases = output.get("cases")
    if not isinstance(cases, list) or len(cases) != len(CASE_IDS):
        raise RuntimeError("Unexpected diagnostic case count")
    if [r.get("case_id") for r in cases] != list(CASE_IDS):
        raise RuntimeError("Diagnostic cases returned in unexpected order")
    for r in cases:
        if r.get("first_status") not in {"fulfilled", "rejected", "pending"}:
            raise RuntimeError("Invalid first task status")
        if not isinstance(r.get("next_started"), bool):
            raise RuntimeError("Invalid next task status")
        if r.get("cleanup") != "finished":
            raise RuntimeError(f"Post-observation cleanup timed out for {r.get('case_id')}")
    return cases


def classify(records: list[dict]) -> dict:
    """Assess observed states without assuming the expected pattern was reproduced."""
    index = {}
    for rec in records:
        key = (rec["repeat"], rec["revision"], rec["case_id"])
        if key in index:
            raise ValueError(f"Duplicate observation {key}")
        index[key] = rec
    repeats = sorted({r["repeat"] for r in records})
    if not repeats or repeats != list(range(1, max(repeats) + 1)):
        raise ValueError("Repeat IDs must be consecutive, starting at 1")
    if set(index) != {(rep, label, cid) for rep in repeats
                      for label in REVISIONS for cid in CASE_IDS}:
        raise ValueError("Incomplete revision/case/repeat grid")

    differences = []
    expected = []
    controls_ok = []
    for rep in repeats:
        for case in CASE_IDS:
            before = index[(rep, "before", case)]
            after = index[(rep, "after", case)]
            fields = ("first_status", "next_started", "next_status", "signal_aborted",
                      "queue_pending", "queue_size")
            differing_fields = [f for f in fields if before.get(f) != after.get(f)]
            if differing_fields:
                differences.append({"repeat": rep, "case_id": case, "fields": differing_fields})
        old = index[(rep, "before", "sync_self_abort")]
        new = index[(rep, "after", "sync_self_abort")]
        expected.append(old.get("first_status") == "pending" and old.get("next_started") is False
                        and new.get("first_status") == "rejected" and new.get("next_started") is True)
        micro_before = index[(rep, "before", "microtask_self_abort")]
        micro_after = index[(rep, "after", "microtask_self_abort")]
        ext_before = index[(rep, "before", "external_abort")]
        ext_after = index[(rep, "after", "external_abort")]
        none_before = index[(rep, "before", "no_abort_control")]
        none_after = index[(rep, "after", "no_abort_control")]
        controls_ok.append(
            all(r.get("first_status") == "rejected" and r.get("next_started") is True
                for r in (micro_before, micro_after, ext_before, ext_after))
            and all(r.get("first_status") == "pending" and r.get("next_started") is False
                    for r in (none_before, none_after))
        )
    return {
        "repeats": len(repeats),
        "total_execution_cases": len(records),
        "differences": differences,
        "sync_expected_per_repeat": expected,
        "control_expectations_per_repeat": controls_ok,
        "historical_pattern_reproduced": all(expected) and all(controls_ok),
    }


def render_md(result: dict) -> str:
    records = result["records"]
    stats = result["analysis"]
    lines = ["# Day 18 — Known-issue p-queue coverage-gap diagnostic", "",
             f"**Evidence:** {NOTE}.", "",
             "This deliberately tests synchronous self-abort during task startup, which was "
             "not expressible in the Day 17 public action grammar.", "",
             "| Case | Before first / next started | After first / next started |",
             "|---|---|---|"]
    index = {(r["repeat"], r["revision"], r["case_id"]): r for r in records}
    for case in CASE_IDS:
        a, b = index[(1, "before", case)], index[(1, "after", case)]
        fmt = lambda r: f"{r['first_status']} / {r['next_started']}"
        lines.append(f"| `{case}` | {fmt(a)} | {fmt(b)} |")
    lines.extend(["",
                  f"Trials per revision/case: **{stats['repeats']}**; total case executions: **{len(records)}**.",
                  f"Expected sync-abort before/after pattern and negative controls reproduced in all repeats: **{stats['historical_pattern_reproduced']}**.",
                  f"Case-pair differences (not unique defects): **{len(stats['differences'])}**.", "",
                  "## Interpretation", "",
                  "- The Day 17 matrix exercised a restricted external-abort grammar and found zero differences.",
                  "- This targeted reproduction tests a different scheduling window: a task aborts its own signal during startup.",
                  "- A successful before/after pattern would validate the **coverage-gap diagnosis**, not AI performance or independent discovery.",
                  "- Public `p-queue` code is unchanged; gate release happens **after** each pre-release observation.",
                  "- Source revisions and built artifacts are checked against the prior Day 15 provenance record.",
                  "- The Day 11 frozen manifest and staged `t01` packet remain untouched. **Do not seal `t01`.**", "",
                  "## Provenance", "",
                  f"Probe SHA-256: `{result['probe_sha256']}`", "",
                  f"Observed revisions: before `{result['commits']['before']}`; after `{result['commits']['after']}`.", "",
                  "Source issue: https://github.com/sindresorhus/p-queue/issues/256", ""])
    if not stats["historical_pattern_reproduced"]:
        lines += ["**Unexpected behavior:** inspect `results/day18_gap_observations.json` rather than interpreting this as a successful reproduction.", ""]
    return "\n".join(lines)


def run(repeats: int = 3, observe_ms: int = 50, root: Path = ROOT) -> dict:
    if not 1 <= repeats <= 20:
        raise ValueError("repeats must be between 1 and 20")
    if not 10 <= observe_ms <= 2000:
        raise ValueError("observe_ms must be between 10 and 2000")
    assert_day11_lock(root)
    bundles = get_source_bundles(root)
    probe = root / PROBE
    records = []
    for repeat in range(1, repeats + 1):
        for label, bundle in bundles.items():
            observed = invoke_node(probe, bundle, observe_ms)
            records.extend({"repeat": repeat, "revision": label, **rec} for rec in observed)
    analysis = classify(records)
    output = {
        "evidence_level": NOTE,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "probe_sha256": sha(probe),
        "commits": dict(REVISIONS),
        "repeats": repeats, "observe_ms": observe_ms,
        "records": records, "analysis": analysis,
    }
    out = root / "results"
    out.mkdir(exist_ok=True)
    (out / OUTPUT_JSON).write_text(canonical_json(output), encoding="utf-8")
    (out / OUTPUT_MD).write_text(render_md(output), encoding="utf-8")
    assert_day11_lock(root)
    return output


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("run", "report"))
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--observe-ms", type=int, default=50)
    args = p.parse_args()
    try:
        if args.command == "run":
            result = run(repeats=args.repeats, observe_ms=args.observe_ms)
            print("Executed:", len(result["records"]), "known-issue case executions")
            print("Historical pattern reproduced:", result["analysis"]["historical_pattern_reproduced"])
            print("Observed paired differences:", len(result["analysis"]["differences"]))
            print("Saved:", ROOT / "results" / OUTPUT_MD)
        else:
            path = ROOT / "results" / OUTPUT_MD
            if not path.is_file():
                raise ValueError("No report exists; run diagnostic first")
            print(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError,
            TypeError, json.JSONDecodeError) as exc:
        p.exit(1, "Day 18: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
