"""Day 16: versioned, read-only three-action feasibility study on p-queue t01.

Commands:
    python -m webstatecheck.day16_three_action audit
    python -m webstatecheck.day16_three_action smoke

This module deliberately DOES NOT alter the frozen Day 11 protocol or the
staged t01 public/private packets. It is a *development amendment proposal*,
not a held-out test, preregistration, AI result, or bug-discovery claim.
"""
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha
from webstatecheck.day14_feasibility import analyze_sequence
from webstatecheck.day15_executor import (
    TARGET, PROBE, SOURCE_DIR, REVISIONS, _run, action_options,
    public_spec, verify_prepared_source,
)

BUDGET_V2 = 3
KIND = "DEVELOPMENT FEASIBILITY ONLY — NOT AI, NOT BLINDED, NOT DEFECT DISCOVERY"

# Each triple is drawn solely from the *public* Day 13 action grammar.
# Observation is currently budgeted, a known problem for a future V2 protocol.
SMOKE_TRIPLES = (
    ("quick", "quick", "observe"),
    ("delayed", "quick", "release"),
    ("delayed", "quick", "observe"),
    ("cancelable", "cancel", "observe"),
    ("delayed", "cancelable", "cancel"),
    ("delayed", "cancelable", "release"),
    ("delayed", "delayed", "release"),
    ("reject", "quick", "observe"),
    ("quick", "cancelable", "cancel"),
    ("cancelable", "quick", "observe"),
    ("delayed", "release", "quick"),
    ("delayed", "cancelable", "observe"),
    ("quick", "delayed", "release"),
    ("cancelable", "cancelable", "cancel"),
)
ALIASES = {
    "quick": ("submit", "enqueue_quick_task"),
    "delayed": ("submit", "enqueue_delayed_task"),
    "reject": ("submit", "enqueue_rejecting_task"),
    "cancelable": ("submit", "enqueue_cancelable_task"),
    "cancel": ("cancel", "current_signal"),
    "release": ("click", "release_delayed_task"),
    "observe": ("click", "observe_idle_status"),
}


def _assert_unmodified_registration(root: Path = ROOT) -> dict:
    assert_day11_lock(root)
    spec = public_spec(root)  # Includes t01 must remain UNSEALED.
    if spec.get("actions_per_scenario") != 2 or spec.get("scenarios_per_method") != 4:
        raise ValueError("Day 13 public registration was changed; stop and investigate")
    return spec


def _three_action_options(root: Path = ROOT) -> list[dict]:
    _assert_unmodified_registration(root)
    return action_options(root)


def enumerate_sequences(options: list[dict]) -> list[dict]:
    """Pure precondition exploration; no revision labels or bugs are used."""
    if not options or len({(x['type'], x['target']) for x in options}) != len(options):
        raise ValueError("Expected nonempty, distinct action grammar")
    rows = []
    for i, seq in enumerate(itertools.product(options, repeat=BUDGET_V2), 1):
        actions = [dict(a) for a in seq]
        result = analyze_sequence(actions)
        rows.append({"plan_id": f"v2-{i:03d}", "actions": actions, **result})
    return rows


def smoke_scenarios(options: list[dict]) -> list[dict]:
    allowed = {(a["type"], a["target"]) for a in options}
    plans = []
    for i, triple in enumerate(SMOKE_TRIPLES, 1):
        pairs = [ALIASES[word] for word in triple]
        if any(pair not in allowed for pair in pairs):
            raise ValueError("Smoke sequence uses an action outside staged public specification")
        actions = [{"type": typ, "target": target} for typ, target in pairs]
        checked = analyze_sequence(actions)
        if not checked["executable_by_preconditions"]:
            raise ValueError(f"Smoke plan {i} fails preconditions: {checked['errors']}")
        plans.append({"plan_id": f"v2-smoke-{i:02d}", "actions": actions})
    return plans


def analyze(root: Path = ROOT) -> dict:
    options = _three_action_options(root)
    rows = enumerate_sequences(options)
    valid = [r for r in rows if r["executable_by_preconditions"]]
    rejected = [r for r in rows if not r["executable_by_preconditions"]]
    return {
        "evidence_level": KIND,
        "budget_v1_frozen": 2,
        "budget_v2_proposed": BUDGET_V2,
        "total_sequences": len(rows),
        "precondition_valid": len(valid),
        "precondition_invalid": len(rejected),
        "valid_with_unreleased_gate": sum(any('unreleased delayed' in w for w in r['warnings']) for r in valid),
        "valid_with_budgeted_observation": sum(any('observation consumes' in w for w in r['warnings']) for r in valid),
        "valid_with_cancellation_action": sum('cancellation_action' in r['patterns'] for r in valid),
        "scope": "static preconditions only, not runtime correctness",
        "candidate_status": "UNSEALED; source/issue known to researchers; development only",
    }


def _write_audit(root: Path, summary: dict) -> None:
    result_dir = root / 'results'
    result_dir.mkdir(exist_ok=True)
    (result_dir / 'day16_three_action_audit.json').write_text(canonical_json(summary), encoding='utf-8')
    text = [
        '# Day 16 — Proposed three-action grammar audit', '',
        '**Development feasibility only. Not blinded, not a discovery benchmark.**', '',
        f"Total action triples: **{summary['total_sequences']}**.",
        f"Pass preconditions: **{summary['precondition_valid']}**.",
        f"Fail preconditions: **{summary['precondition_invalid']}**.",
        f"Valid with unreleased delayed gate: **{summary['valid_with_unreleased_gate']}**.",
        f"Valid with observation consuming action budget: **{summary['valid_with_budgeted_observation']}**.",
        f"Valid with explicit cancellation action: **{summary['valid_with_cancellation_action']}**.",
        '',
        'The registered t01 two-action specification and all nine Day 11 frozen files remain unchanged.',
        'This proposes a versioned change only for future independent studies. A separate registration,',
        'new target(s), and isolated test generation are required before any held-out comparison.', '',
    ]
    (result_dir / 'day16_three_action_audit.md').write_text('\n'.join(text), encoding='utf-8')


def run_smoke(root: Path = ROOT) -> dict:
    """Run representative triples against the Day 15 source-pinned runner."""
    repo = verify_prepared_source(root)
    options = _three_action_options(root)
    runner = root / PROBE
    if not runner.is_file():
        raise ValueError('Day 15 Node executor missing')
    plans = smoke_scenarios(options)
    rows = []
    builds = json.loads((root / 'results' / 'day15_build_provenance.json').read_text(encoding='utf-8'))
    for revision, commit in REVISIONS.items():
        checkout = root / SOURCE_DIR / 'versions' / revision
        if _run(['git', 'rev-parse', 'HEAD'], cwd=checkout) != commit:
            raise ValueError(f'Unexpected {revision} Git commit; refusing experiment')
        bundle = checkout / 'dist/index.js'
        expected_bundle_hash = builds.get('bundles', {}).get(revision, {}).get('sha256')
        if not bundle.is_file() or not expected_bundle_hash or sha(bundle) != expected_bundle_hash:
            raise ValueError(f'{revision} build missing or changed since Day 15 provenance check')
        payload = {'target_id': TARGET, 'scenarios': plans, 'max_wait_ms': 5000}
        proc = subprocess.run(['node', str(runner), str(bundle)], input=canonical_json(payload),
                              capture_output=True, text=True, cwd=repo, timeout=90, check=False)
        if proc.returncode:
            raise RuntimeError(f'Node executor error on {revision}: {proc.stderr[-1200:]}')
        result = json.loads(proc.stdout)
        observed = result.get('records', [])
        if result.get('target_id') != TARGET or len(observed) != len(plans):
            raise RuntimeError('Executor did not return one result per scenario')
        expected_ids = {p['plan_id'] for p in plans}
        if {r.get('plan_id') for r in observed} != expected_ids:
            raise RuntimeError('Missing, unexpected or duplicate scenario IDs')
        for r in observed:
            if r.get('status') not in ('settled', 'needs_release', 'unresolved'):
                raise RuntimeError('Unknown verdict/status from executor')
            rows.append({'revision': revision, 'commit': commit, **r})
    stats = {}
    for revision in REVISIONS:
        subset = [r for r in rows if r['revision'] == revision]
        count = Counter(r['status'] for r in subset)
        stats[revision] = {
            'executed': len(subset),
            'settled': count['settled'], 'needs_release': count['needs_release'],
            'unresolved': count['unresolved'],
            'capacity_violations': sum(r.get('max_active', 0) > 1 for r in subset),
        }
    # Differences are observational. They are not assigned bug labels.
    before = {r['plan_id']: r for r in rows if r['revision'] == 'before'}
    after = {r['plan_id']: r for r in rows if r['revision'] == 'after'}
    differing_status_ids = [p['plan_id'] for p in plans
                            if before[p['plan_id']]['status'] != after[p['plan_id']]['status']]
    result = {
        'evidence_level': KIND, 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'study': 'v2 proposed 3-action feasibility, t01 development case',
        'frozen_protocol_untouched': True,
        'public_spec_sha256': sha(root / 'research/holdout_staging/t01/public_spec.json'),
        'plan_count_per_revision': len(plans), 'budget_actions_per_plan': BUDGET_V2,
        'summary': stats, 'status_differences': differing_status_ids,
        'records': rows,
    }
    out = root / 'results'
    out.mkdir(exist_ok=True)
    (out / 'day16_smoke_observations.json').write_text(canonical_json(result), encoding='utf-8')
    lines = [
        '# Day 16 — Three-action prototype feasibility smoke test', '',
        '**Development only, known source/fix case. NOT blinded or AI-generated.**', '',
        'Same 14 three-action scenarios applied to actual source-pinned `p-queue` versions.',
        'Unreleased delays are recorded as `needs_release`, not a clean pass.', '',
        '| Revision | Scenarios | Settled | Needs release | Unresolved | Capacity violations |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for label, v in stats.items():
        lines.append(f"| {label} | {v['executed']} | {v['settled']} | {v['needs_release']} | {v['unresolved']} | {v['capacity_violations']} |")
    lines += ['', 'Scenarios with a different *status* between revisions: '
              + (', '.join(differing_status_ids) if differing_status_ids else 'none observed'), '',
              '## Interpretation', '',
              '- Outcome differences do not automatically establish historical bugs.',
              '- Three actions allow additional task/cancel/release interleavings.',
              '- `observe_idle_status` still spends an action slot, so future protocols should reconsider it.',
              '- Cleanup occurs only after observations, not as a budget-free part of a test.',
              '- This run does not assess a frozen held-out benchmark, AI superiority, or novelty.',
              '- Neither the Day 11 frozen protocol nor the staged t01 registration has been changed.', '']
    (out / 'day16_smoke_summary.md').write_text('\n'.join(lines), encoding='utf-8')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['audit', 'smoke'])
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            summary = analyze()
            _write_audit(ROOT, summary)
            print(f"Three-action sequences: {summary['total_sequences']}; pass: {summary['precondition_valid']}; "
                  f"fail: {summary['precondition_invalid']}")
            print('Saved:', ROOT / 'results/day16_three_action_audit.md')
        else:
            result = run_smoke()
            for label, record in result['summary'].items():
                print(label, record)
            print('Saved:', ROOT / 'results/day16_smoke_summary.md')
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError,
            json.JSONDecodeError) as e:
        parser.exit(1, 'Day 16: ' + str(e) + '\n')


if __name__ == '__main__':
    main()
