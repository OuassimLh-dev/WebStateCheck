"""Day 23: provenance-checked readiness audit for a future independent study.

Reanalyzes previously saved Day 22 data; DOES NOT run applications, score bugs,
generate model plans, change frozen files, or seal target t01.

Usage:
  python -m webstatecheck.day23_readiness audit
  cat results/day23_readiness_summary.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from webstatecheck import day22_pairing as d22
from webstatecheck import day21_adapter as d21
from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha

SUMMARY = Path('results/day23_readiness_summary.md')
JSON_OUTPUT = Path('results/day23_readiness.json')

# A successful programmatic audit cannot approve a prospective study.
PENDING_REQUIREMENTS = {
    'new_independently_selected_targets': 'No new target registered and screened independently for prospective scoring',
    'independent_oracle_review': 'No external reviewer has approved source-independent correctness criteria and ambiguous outcomes',
    'isolated_model_generation': 'No isolated model prompt/version/settings, generated candidates, retry budget or cost record',
    'preregistered_v2_design': 'No separately frozen v2 protocol with target-level budgets, outcome adjudication and leakage controls',
}


def inspect(root: Path = ROOT) -> dict[str, Any]:
    """Validate saved provenance/observations and label remaining evidence gaps.

    This does not establish independent correctness of observed task behavior.
    """
    lock_hash = assert_day11_lock(root)
    folds, manifest = d22.load_folds(root)
    path = root / d22.FACTORIAL_JSON
    if not path.is_file():
        raise FileNotFoundError('Day 22 factorial observations missing; run day22_pairing run first')
    report = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(report, dict):
        raise ValueError('Day 22 report must be a JSON object')
    if (report.get('heldout') is not False or report.get('llm_generated') is not False
            or report.get('classification') != 'DAY22 DEVELOPMENT FACTORIAL, NOT HOLDOUT'):
        raise ValueError('Day 22 provenance classification is missing or inconsistent')
    if report.get('plan_sha256') != manifest.get('plan_sha256'):
        raise ValueError('Day 22 plan SHA-256 does not match prepared manifest')
    if report.get('runner_sha256') != sha(root / d21.RUNNER):
        raise ValueError('Day 22 runtime runner hash mismatch')
    repeats = report.get('repeats')
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError('Day 22 repeat count invalid')
    records = report.get('records')
    if not isinstance(records, list):
        raise ValueError('Day 22 records missing')
    recomputed = d22.analyze_factorial(records, folds, repeats)
    if report.get('analysis') != recomputed:
        raise ValueError('Day 22 saved analysis is not reproducible from its observations')

    # Calculate unique underlying experimental cells, not repeated changed pairs.
    per_cell = {}
    for label, cell in recomputed['cells'].items():
        trials = cell['trials']
        per_cell[label] = {
            'repeats': len(trials),
            'paired_observational_changes': cell['changed_repeat_count'],
            'changed_fields': sorted({f for t in trials for f in t['different_fields']}),
            'before_first_status': [t['before_first'] for t in trials],
            'after_first_status': [t['after_first'] for t in trials],
            'before_next_started': [t['before_next_started'] for t in trials],
            'after_next_started': [t['after_next_started'] for t in trials],
        }
    unique_cells = len([v for v in per_cell.values() if v['paired_observational_changes']])
    repeat_changes = sum(v['paired_observational_changes'] for v in per_cell.values())
    if repeat_changes != recomputed['changed_paired_executions']:
        raise ValueError('Unique-cell accounting differs from execution accounting')
    counts = Counter(row['revision'] for row in records)
    if counts != Counter({'before': 4 * repeats * 2, 'after': 4 * repeats * 2}):
        raise ValueError('Unexpected number of per-revision observations')
    if recomputed['resource_totals']['fold_a'] != recomputed['resource_totals']['fold_b']:
        raise ValueError('Actual resource totals not balanced')

    integrity = {
        'day11_lock': 'verified',
        'provenance_hashes': 'verified',
        'execution_grid_and_resource_counters': 'verified',
        'saved_analysis_recomputed': 'verified',
        'source_independent_oracle': 'not_verified',
    }
    result = {
        'classification': 'RETROSPECTIVE DEVELOPMENT READINESS AUDIT — NOT A HELD-OUT RESULT',
        'source_file_sha256': sha(path),
        'day11_lock_sha256': lock_hash,
        'day22_plan_sha256': manifest['plan_sha256'],
        'day22_runner_sha256': report['runner_sha256'],
        'executions': recomputed['executions'],
        'repeats': repeats,
        'timing_profile_cells': len(per_cell),
        'changed_execution_pairs': repeat_changes,
        'changed_distinct_cells': unique_cells,
        'changed_cell_names': sorted(k for k, v in per_cell.items() if v['paired_observational_changes']),
        'repeat_instability': len(recomputed['repeat_instability']),
        'balanced_execution_costs': True,
        'per_cell': per_cell,
        'artifact_integrity': integrity,
        'prospective_gates': {key: {'status': 'NOT_VERIFIED', 'reason': reason}
                              for key, reason in PENDING_REQUIREMENTS.items()},
        'ready_for_blinded_study': False,
        'heldout_targets_registered_by_this_tool': 0,
        'ai_plans_generated_by_this_tool': 0,
    }
    assert_day11_lock(root)
    return result


def render(result: dict) -> str:
    lines = [
        '# Day 23 — Independent-evaluation readiness audit', '',
        '**Status: NOT READY FOR A BLINDED STUDY.** This is a retrospective audit of the known `p-queue` development case.', '',
        f"Evidence: **{result['executions']}** actual executions, **{result['timing_profile_cells']}** timing/profile cells, **{result['repeats']}** repeats per cell/revision.",
        f"Before/after differing execution pairs: **{result['changed_execution_pairs']}**; distinct changed cells: **{result['changed_distinct_cells']}**.",
        f"Within-revision repeat instability: **{result['repeat_instability']}**; actual fold resource totals equal: **{result['balanced_execution_costs']}**.", '',
        '| Timing × completion profile | Changed paired repeats | Distinct changed fields |',
        '|---|---:|---|',
    ]
    for label in sorted(result['per_cell']):
        row = result['per_cell'][label]
        lines.append(f"| `{label}` | {row['paired_observational_changes']} | "
                     + (', '.join('`' + f + '`' for f in row['changed_fields']) or '—') + ' |')
    lines += ['', '## Provenance and consistency checks', '',
              f"- Day 22 raw-observation SHA-256: `{result['source_file_sha256']}`",
              f"- Day 11 frozen lock SHA-256: `{result['day11_lock_sha256']}`",
              '- Plan and runner hashes match; the execution grid and actual operation counters revalidate.',
              '- Saved Day 22 analysis is reproduced from the original observation rows.',
              '- These consistency checks do **not** independently validate the behavioral oracle.', '',
              '## Requirements not yet satisfied', '']
    for key, info in result['prospective_gates'].items():
        lines.append(f"- **{key.replace('_', ' ').title()}** — {info['reason']}.")
    lines += ['', '## Research interpretation', '',
              '- Repeated differences from the same scenario are not unique defects.',
              '- The eight cells were deliberately chosen after learning the known issue, so they are **development evidence**.',
              '- This study does not compare an independently generated LLM plan to other strategies.',
              '- A future study needs independently approved oracles, a new v2 cohort and generation inputs isolated from historical fix details.',
              '- Do **not** seal `t01` or modify the nine Day 11 frozen files. This command only writes new Day 23 results.', '',
              'See `research/DAY23_V2_REVIEW_CHECKLIST.md` for the prospective-study approval checklist.', '']
    return '\n'.join(lines)


def audit(root: Path = ROOT) -> dict:
    result = inspect(root)
    (root / SUMMARY).parent.mkdir(parents=True, exist_ok=True)
    (root / JSON_OUTPUT).write_text(canonical_json(result), encoding='utf-8')
    (root / SUMMARY).write_text(render(result), encoding='utf-8')
    assert_day11_lock(root)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['audit'])
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            report = audit()
            print(f"Audited: {report['executions']} executions; {report['changed_distinct_cells']} distinct changed cell(s)")
            print('Saved evidence provenance and execution-budget checks: verified')
            print('Ready for prospective blinded comparison: NO (independent prerequisites missing)')
            print('Saved:', ROOT / SUMMARY)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f'Day 23 readiness audit: {exc}\n')


if __name__ == '__main__':
    main()
