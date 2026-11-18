"""Day 10: aggregate Day 9 three-method development pilot results.

This is deliberately NOT a measure of real-world detection precision/recall.
Each strategy must have four two-query plans on both fixture versions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from webstatecheck.day9_plans import get_path, validate_plan

ROOT = Path(__file__).resolve().parent.parent
METHODS = ("random", "heuristic", "llm")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def summarize(root: Path) -> dict:
    rows = []
    for method in METHODS:
        plan_file = get_path(method, root)
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        budget = validate_plan(plan, method)
        if budget != {"method": method, "scenarios": 4, "actions": 8}:
            raise ValueError(f"Unexpected test budget for {method}: {budget}")
        result_file = root / "results" / f"day9_{method}_observations.json"
        data = json.loads(result_file.read_text(encoding="utf-8"))
        if data.get("method") != method or data.get("plan_sha256") != sha256(plan_file):
            raise ValueError(f"Method or plan SHA-256 mismatch for {method}; rerun this method")
        if data.get("scenarios_per_version") != 4 or data.get("actions_per_version") != 8:
            raise ValueError(f"Mismatched budget in results for {method}")
        observations = data.get("observations", [])
        if len(observations) != 8:
            raise ValueError(f"Expected exactly 8 executed observations for {method}")
        for mode in ("buggy", "fixed"):
            matching = [v for v in observations if v.get("mode_for_analysis_only") == mode]
            if len(matching) != 4:
                raise ValueError(f"Expected four {mode} observations for {method}")
            verdicts = [v.get("verdict") for v in matching]
            if any(v not in ("violation", "clear", "inconclusive") for v in verdicts):
                raise ValueError(f"Unexpected verdict for {method}/{mode}")
            rows.append({"method":method, "version":mode,
                        "violations":verdicts.count("violation"),
                        "clear":verdicts.count("clear"),
                        "inconclusive":verdicts.count("inconclusive"),
                        "issue_types":sorted({issue for v in matching for issue in v.get("issues", [])}),
                        "mean_ms_check":round(sum(v["elapsed_ms"] for v in matching)/len(matching),1),
                        "plan_sha256":sha256(plan_file)})
    return {"study":"Day10 development-only comparison, not a blind study",
            "methods":list(METHODS), "scenarios_per_version":4,
            "actions_per_version":8, "rows":rows}


def render_md(report: dict) -> str:
    lines = ["# Day 10 — Development-only AI plan comparison", "",
             "**CAUTION:** Synthetic fixture known to both researcher and assistant. The 'LLM' candidate was composed in an ongoing ChatGPT conversation with prior test results in context, NOT a clean independent model session. The test selectors are still fixture-specific. These results cannot establish AI superiority, real-world accuracy, or novel defect discovery.", "",
             "All methods: four two-query plans (= 8 actions) per application version. Same browser runner/oracle.", "",
             "| Method | Version | Violations | Clear | Inconclusive | Issue types | Mean ms/check |",
             "|---|---|---:|---:|---:|---|---:|"]
    for v in report["rows"]:
        lines.append(f'| {v["method"]} | {v["version"]} | {v["violations"]} | {v["clear"]} | {v["inconclusive"]} | {", ".join(v["issue_types"]) or "—"} | {v["mean_ms_check"]} |')
    lines += ["", "## Limitations", "",
              "- Four scenarios per strategy are too few for inferential statistics.",
              "- Models and heuristics have prior knowledge of this fixture; no holdout.",
              "- 'Issue types' counts categories, NOT unique independently confirmed defects.",
              "- Model token cost and generation time are not measured; runtime is browser check time only.",
              "- A fair future study needs frozen prompts/models, independently selected cases, comparable budgets and unbiased oracles.", ""]
    return "\n".join(lines)


def main() -> None:
    try:
        report = summarize(ROOT)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, KeyError) as exc:
        raise SystemExit(f"Cannot compare Day 9 methods: {exc}") from exc
    out = ROOT / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "day10_comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    mdpath = out / "day10_comparison_summary.md"
    mdpath.write_text(render_md(report), encoding="utf-8")
    print(render_md(report))
    print("Saved:", mdpath)


if __name__ == "__main__":
    main()
