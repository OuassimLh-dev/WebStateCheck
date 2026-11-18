"""Day 8: cross-project casebook of existing experimental observations.

Offline. Re-evaluates the rule engine on previously saved browser, Final Form,
and Axios records. The source/revision label is deliberately excluded from
invariant evaluation. No new experiments, AI inference, or autonomous discovery.

Run: python -m webstatecheck.day8_casebook
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day6_oracles import browser_facts, final_form_facts, evaluate_rules
from webstatecheck.day7_axios import axios_facts

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RULE_DIR = ROOT / "research" / "oracles"

INPUTS = {
    "browser": "day4_observations.json",
    "final_form": "day5_realworld.json",
    "axios": "day7_axios_observations.json",
}


def load_json(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"Missing required evidence file: {path}\nRun the relevant Day 4, 5, or 7 experiment first.")
    return json.loads(path.read_text(encoding="utf-8"))


def get_rules(root: Path):
    day6 = load_json(root / "research" / "oracles" / "day6_rules.json")["rules"]
    day7 = load_json(root / "research" / "oracles" / "day7_axios_rules.json")["rules"]
    all_rules = day6 + day7
    sources = {"browser", "final_form", "axios"}
    if not all_rules or any(r.get("source") not in sources or not r.get("when") or not r.get("require") for r in all_rules):
        raise ValueError("Malformed rule configuration")
    identifiers = [r["id"] for r in all_rules]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate rule IDs")
    return all_rules


def process_observation(source: str, raw: dict, rules: list[dict], index: int) -> dict:
    """Evaluate solely on factual observations, never revision labels or expected bugs."""
    if source == "browser":
        facts = browser_facts(raw)
        previous = "inconclusive" if raw.get("inconclusive") else "violation" if raw.get("observed_violation") else "clear"
        label = raw.get("mode", "unknown")
        scenario = ",".join(raw.get("queries") or [])
    elif source == "final_form":
        facts = final_form_facts(raw)
        previous = "violation" if raw.get("violation") is True else "clear" if raw.get("violation") is False else None
        label = raw.get("label", "unknown")
        scenario = "old_validator_finishes_while_new_pending"
    elif source == "axios":
        facts = axios_facts(raw)
        previous = raw.get("verdict")
        label = raw.get("label", "unknown")
        scenario = raw.get("scenario", "unknown")
    else:
        raise ValueError(f"Unsupported evidence source: {source}")
    assessment = evaluate_rules(source, facts, rules)
    return {
        "id": f"{source}-{index}",
        "source": source,
        "scenario": scenario,
        "facts": facts,
        "verdict": assessment["verdict"],
        "rule_results": assessment["rules"],
        # All following fields are used for analysis only, AFTER evaluation.
        "label_for_analysis_only": label,
        "previous_verdict_for_analysis_only": previous,
        "upstream_commit_for_provenance": raw.get("upstream_commit") if source != "browser" else None,
    }


def aggregate(records: list[dict]) -> dict:
    groups = defaultdict(lambda: Counter())
    for row in records:
        groups[(row["source"], row["label_for_analysis_only"])][row["verdict"]] += 1
    return {
        f"{source}:{label}": {
            "cases": sum(counts.values()),
            **{verdict: counts[verdict] for verdict in ("violation", "clear", "inconclusive", "not_covered")},
        }
        for (source, label), counts in sorted(groups.items())
    }


def run(root: Path = ROOT, output: Path | None = None) -> dict:
    root = Path(root)
    evidence_dir = root / "results"
    output = Path(output) if output is not None else evidence_dir
    rules = get_rules(root)
    records = []
    source_evidence = {}
    for source, basename in INPUTS.items():
        path = evidence_dir / basename
        blob = path.read_bytes() if path.is_file() else None
        if blob is None:
            raise FileNotFoundError(f"Missing {path}; finish that experiment before running Day 8.")
        raw = json.loads(blob)
        observations = raw.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError(f"Expected nonempty observations list in {path}")
        source_evidence[source] = {
            "path": str(path),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "records": len(observations),
        }
        records.extend(process_observation(source, r, rules, i) for i, r in enumerate(observations, 1))
    grouped = aggregate(records)
    discrepancies = [r for r in records if r["previous_verdict_for_analysis_only"] is not None and r["verdict"] != r["previous_verdict_for_analysis_only"]]
    verdict_totals = Counter(r["verdict"] for r in records)
    result = {
        "study": "Day 8 cross-project casebook (existing observations only)",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "No new experiments, AI execution or autonomous bug discovery.",
            "Synthetic browser cases and targeted upstream regression reproductions are not independent discovery benchmarks.",
            "Rules and adapters were written with knowledge of the studied bugs.",
            "Repetitions are correlated, not new projects; do not calculate general accuracy from this table.",
        ],
        "evidence": source_evidence,
        "cases": len(records),
        "totals": dict(verdict_totals),
        "groups": grouped,
        "disagreement_count": len(discrepancies),
        "disagreements": [{"id":r["id"], "old":r["previous_verdict_for_analysis_only"], "new":r["verdict"]} for r in discrepancies],
        "observations": records,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "day8_casebook.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = [
        "# Day 8 — Cross-project evidence casebook", "",
        "**Evidence level:** Reanalysis of existing Day 4, Day 5, and Day 7 observations. **Not a new experiment or AI result.**", "",
        f"Cases inspected: **{len(records)}** · Disagreements with saved prior verdicts: **{len(discrepancies)}**", "",
        "| Source | Revision / mode | Cases | Violation | Clear | Inconclusive | Not covered |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, values in grouped.items():
        source, label = group.split(":", 1)
        rows.append(f'| {source} | {label} | {values["cases"]} | {values["violation"]} | {values["clear"]} | {values["inconclusive"]} | {values["not_covered"]} |')
    rows.extend(["", "## Provenance (input SHA-256)", ""])
    for source, p in source_evidence.items():
        rows.append(f'- `{source}`: `{p["sha256"]}` ({p["records"]} saved observations)')
    rows += [
        "", "## Interpretation and limitations", "",
        "- Browser data are from one deliberately seeded fixture, not a real-world project.",
        "- Final Form is a targeted known-bug reproduction of one actual upstream issue.",
        "- Axios is an isolated real upstream module with one stubbed dependency; no HTTP integration was exercised.",
        "- Rule evaluation does **not** use buggy/fixed labels, but rules and input adapters were authored with knowledge of the cases.",
        "- Agreement with saved checks is a consistency check, **not** independent accuracy, recall, or generalization.",
        "- AI-generated plans and novel defect discovery have **not** been evaluated.",
        "", "## Next experiment design", "",
        "1. Freeze the candidate generator, test budgets, and oracle protocol before looking at a NEW holdout bug.",
        "2. Compare random selection, non-AI guided selection, and a documented LLM-generated strategy on the same held-out systems.",
        "3. Score discovered *unique defects*, false positives, inconclusive outcomes, and wall-clock time, not just repeated detections.",
        "4. Document every prompt, model/version, date, inputs, budget, and generated candidate test before executing it.",
        "", "## Rule disagreements", "",
    ]
    if not discrepancies:
        rows.append("No disagreements with saved targeted oracle verdicts on these records.")
    else:
        for r in discrepancies[:20]:
            rows.append(f'- `{r["id"]}`: saved `{r["previous_verdict_for_analysis_only"]}`, new `{r["verdict"]}`')
    (output / "day8_casebook_summary.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = run(output=args.output)
    except (FileNotFoundError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Day 8 failed: {exc}\n")
    print(f'Inspected {data["cases"]} saved observations, {data["disagreement_count"]} disagreement(s).')
    print('Saved:', (args.output or RESULTS) / "day8_casebook_summary.md")


if __name__ == "__main__":
    main()
