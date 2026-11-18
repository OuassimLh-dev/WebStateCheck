"""Inspect every disagreement against the original Day 4 targeted oracle.

Run: python -m webstatecheck.day6_audit
This reads saved files only. It never edits observations or their verdicts.
"""
from __future__ import annotations
import json
from pathlib import Path
from .day6_oracles import DEFAULT_RULES, ROOT, browser_facts, evaluate_rules, load_json


def main():
    data = load_json(ROOT / "results/day4_observations.json")
    rules = load_json(DEFAULT_RULES)["rules"]
    disagreements = []
    for i, row in enumerate(data["observations"], 1):
        prior = "inconclusive" if row.get("inconclusive") else "violation" if row.get("observed_violation") else "clear"
        facts = browser_facts(row)
        new = evaluate_rules("browser", facts, rules)
        if prior != new["verdict"]:
            disagreements.append((i, row, prior, facts, new))
    print(f"Browser observations: {len(data['observations'])}")
    print(f"Disagreements: {len(disagreements)}")
    for i,row,prior,facts,new in disagreements[:10]:
        print(f"\nObservation browser-{i}: {row.get('strategy')} {row.get('mode')} {row.get('queries')}")
        print(f"Previous: {prior}; declarative: {new['verdict']}")
        print("Prior issues:", row.get("issues"))
        print("UI state:", row.get("ui_state"))
        print("Facts:", json.dumps(facts, sort_keys=True))
        print("Rule outcomes:", new["rules"])
    if len(disagreements) > 10:
        print(f"... and {len(disagreements)-10} further disagreements")

if __name__ == "__main__":
    main()
