"""Day 19: parameterized async-timing *development* probe for p-queue.

Run:
  python -m webstatecheck.day19_timing validate
  python -m webstatecheck.day19_timing run --repeats 3
  cat results/day19_timing_summary.md

NO blinded evaluation, autonomous test generation, or newly discovered defect is claimed.
This tool never modifies the frozen Day 11 files or the staged t01 registration.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha
from webstatecheck.day18_gap_diagnostic import get_source_bundles

SCHEMA = 'wsc-timing-dev-v1'
TARGET = 't01'
TIMINGS = ('in_callback_sync', 'in_callback_microtask', 'after_submit_external', 'none')
PROFILES = ('gated', 'immediate')
PLANS = Path('research/day19_development_plans.json')
RUNNER = Path('realworld/p_queue_holdout/day19_timing_runner.mjs')
DAY18_MAPPING = {
    'in_callback_sync': 'sync_self_abort',
    'in_callback_microtask': 'microtask_self_abort',
    'after_submit_external': 'external_abort',
    'none': 'no_abort_control',
}
NOTE = 'Development-only known-issue timing-grammar diagnostic; not blinded, not AI-generated, not novel discovery'
ID_PATTERN = re.compile(r'^[a-z][a-z0-9-]{1,40}$')


def validate_plan_object(plan: object) -> dict:
    """Strict input validation: malformed plans do not become inconclusive test results."""
    if not isinstance(plan, dict) or set(plan) != {'schema_version', 'target_id', 'plans'}:
        raise ValueError('Plan must contain schema_version, target_id and plans only')
    if plan['schema_version'] != SCHEMA or plan['target_id'] != TARGET:
        raise ValueError('Wrong timing plan schema/target')
    scenarios = plan['plans']
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 16:
        raise ValueError('Expect 1..16 timing plans')
    ids = set()
    for row in scenarios:
        if not isinstance(row, dict) or set(row) != {'plan_id', 'first_task', 'abort_timing'}:
            raise ValueError('Each plan needs plan_id, first_task and abort_timing only')
        name = row['plan_id']
        if not isinstance(name, str) or ID_PATTERN.fullmatch(name) is None or name in ids:
            raise ValueError('Invalid or duplicate plan id')
        ids.add(name)
        if row['first_task'] not in PROFILES or row['abort_timing'] not in TIMINGS:
            raise ValueError(f'Invalid timing or first-task profile for {name}')
    return {'scenarios': len(scenarios), 'profiles': dict(Counter(p['first_task'] for p in scenarios)),
            'timings': dict(Counter(p['abort_timing'] for p in scenarios)),
            'task_submissions_per_plan': 2,
            'external_abort_counts_as_extra_mutation': True}


def load_plans(root: Path = ROOT) -> tuple[dict, dict]:
    source = root / PLANS
    plan = json.loads(source.read_text(encoding='utf-8'))
    stats = validate_plan_object(plan)
    return plan, stats


def invoke_node(runner: Path, bundle: Path, request: dict) -> list[dict]:
    if not runner.is_file():
        raise ValueError('Missing Day 19 JS runner; reinstall addon')
    proc = subprocess.run(['node', str(runner), str(bundle)],
                          input=canonical_json(request), text=True, capture_output=True,
                          timeout=45, check=False)
    if proc.returncode != 0:
        raise RuntimeError('Day 19 JS failed: ' + proc.stderr[-2400:])
    try:
        response = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Day 19 JS emitted invalid JSON') from exc
    records = response.get('records')
    if response.get('schema_version') != SCHEMA or not isinstance(records, list):
        raise RuntimeError('Invalid node response shape')
    expected_ids = [p['plan_id'] for p in request['plans']]
    if [r.get('plan_id') for r in records] != expected_ids:
        raise RuntimeError('Missing, duplicated or reordered plans in node response')
    for plan, row in zip(request['plans'], records):
        if row.get('abort_timing') != plan['abort_timing'] or row.get('first_task') != plan['first_task']:
            raise RuntimeError('Node returned mismatched plan values')
        if row.get('first_status') not in ('pending', 'fulfilled', 'rejected'):
            raise RuntimeError('Unexpected first task status')
        if row.get('next_status') not in ('pending', 'fulfilled', 'rejected'):
            raise RuntimeError('Unexpected second task status')
        if type(row.get('next_started')) is not bool:
            raise RuntimeError('Unexpected next_started value')
        if row.get('task_submissions') != 2 or row.get('external_abort_mutations') != int(plan['abort_timing'] == 'after_submit_external'):
            raise RuntimeError('Inconsistent operation accounting')
        if row.get('cleanup') != 'finished':
            raise RuntimeError('Post-observation cleanup did not complete; cannot use observations')
    return records


def analyze(records: list[dict], planned: list[dict], repeats: int) -> dict:
    by_key = {}
    for row in records:
        key = (row['repeat'], row['revision'], row['plan_id'])
        if key in by_key:
            raise ValueError('Duplicate observation ' + str(key))
        by_key[key] = row
    expected = {(repeat, revision, plan['plan_id']) for repeat in range(1, repeats + 1)
                for revision in ('before', 'after') for plan in planned}
    if set(by_key) != expected:
        raise ValueError('Incomplete observation grid')
    fields = ('first_status', 'first_error', 'next_started', 'next_status', 'signal_aborted',
              'queue_pending', 'queue_size', 'queue_error_events')
    differences = []
    instability = []
    for plan in planned:
        pid = plan['plan_id']
        for repeat in range(1, repeats + 1):
            a = by_key[(repeat, 'before', pid)]
            b = by_key[(repeat, 'after', pid)]
            changed = [field for field in fields if a.get(field) != b.get(field)]
            if changed:
                differences.append({'repeat': repeat, 'plan_id': pid, 'fields': changed})
        for revision in ('before', 'after'):
            observations = [{field: by_key[(repeat, revision, pid)].get(field)
                             for field in fields} for repeat in range(1, repeats + 1)]
            if any(observation != observations[0] for observation in observations[1:]):
                instability.append({'plan_id': pid, 'revision': revision})
    return {'total_executions': len(records), 'paired_differences': differences,
            'repeat_instability': instability,
            'unique_changed_plans': sorted({x['plan_id'] for x in differences})}


def compare_day18(root: Path, records: list[dict], observe_ms: int) -> dict:
    """Cross-check comparable gated rows against the saved independent Day 18 probe.

    This is an implementation consistency check, NOT independent bug confirmation.
    """
    prior_path = root / 'results/day18_gap_observations.json'
    if not prior_path.is_file():
        return {'available': False, 'compared': 0, 'mismatches': [], 'reason': 'Day 18 raw records missing'}
    prior = json.loads(prior_path.read_text(encoding='utf-8'))
    if prior.get('observe_ms') != observe_ms:
        return {'available': True, 'compared': 0, 'mismatches': [], 'reason': 'Observation window differs'}
    previous = {(r['repeat'], r['revision'], r['case_id']): r for r in prior.get('records', [])}
    mismatches = []
    compared = 0
    for row in records:
        if row['first_task'] != 'gated' or row['abort_timing'] not in DAY18_MAPPING:
            continue
        key = (row['repeat'], row['revision'], DAY18_MAPPING[row['abort_timing']])
        if key not in previous:
            continue
        compared += 1
        for field in ('first_status', 'next_started', 'next_status', 'signal_aborted'):
            if row.get(field) != previous[key].get(field):
                mismatches.append({'repeat': row['repeat'], 'revision': row['revision'],
                                   'plan_id': row['plan_id'], 'field': field,
                                   'day18': previous[key].get(field), 'day19': row.get(field)})
    return {'available': True, 'compared': compared, 'mismatches': mismatches,
            'reason': 'Shared fields agree' if not mismatches and compared else 'Review mismatches or missing rows'}


def render(report: dict) -> str:
    rows = report['records']
    by_key = {(r['repeat'], r['revision'], r['plan_id']): r for r in rows}
    notes = [
        '# Day 19 — Data-driven cancellation-timing grammar (development)', '',
        '**KNOWN-ISSUE DEVELOPMENT STUDY. NOT A HELD-OUT AI BENCHMARK OR NEW DEFECT DISCOVERY.**', '',
        f"Test plans: **{report['plan_stats']['scenarios']}** · trials per plan/revision: **{report['repeats']}** · actual executions: **{len(rows)}**.",
        f"Saved plan SHA-256: `{report['plans_sha256']}`; JS runner SHA-256: `{report['runner_sha256']}`.", '',
        '| Plan | Before first / next started | After first / next started | Revision-pair changes (trials) |',
        '|---|---|---|---:|',
    ]
    counts = Counter(x['plan_id'] for x in report['analysis']['paired_differences'])
    for plan in report['plans']:
        pid = plan['plan_id']
        before, after = by_key[(1, 'before', pid)], by_key[(1, 'after', pid)]
        notes.append(f"| `{pid}` | {before['first_status']} / {before['next_started']} | "
                     f"{after['first_status']} / {after['next_started']} | {counts[pid]} |")
    notes.extend([
        '',
        f"Revision-paired cases with any observed-field difference: **{len(report['analysis']['paired_differences'])}**.",
        f"Plans exhibiting a revision difference: **{len(report['analysis']['unique_changed_plans'])}**.",
        f"Within-revision repeat instability: **{len(report['analysis']['repeat_instability'])}**.",
        f"Comparison to Day 18 gated-case outcomes (same observe_ms): **{report['day18_check']['compared']}** rows, "
        f"**{len(report['day18_check']['mismatches'])}** mismatched fields.", '',
        '## Protocol and accounting', '',
        '- Each scenario submits two tasks to a fresh single-concurrency queue, with a bounded pre-cleanup observation.',
        '- Abort timing is a **task-body behavior parameter**, not one of the original Day 17 actions.',
        '- External abort is an additional API mutation; action budgets are **NOT equalized across timing modes**.',
        '- Deferred gates are released only after the observed state is recorded.',
        '- Source revisions/bundles are verified against pinned upstream build provenance.',
        '- This test plan was prepared **after learning the historical bug**. It measures expressivity, not discovery.',
        '- Comparing the new runner with Day 18 is a consistency check, not an independent oracle.',
        '- The frozen Day 11 files and staged t01 packet remain unchanged; **do not seal t01**.', '',
        '## Next decision', '',
        'Design a target-independent, versioned scheduling grammar and equal-cost budget that includes program structure',
        'and the possibility of cancellation *inside* task callbacks. Freeze and test it on NEW targets using an isolated',
        'generation context; avoid using this known issue to claim LLM advantage.', '',
    ])
    return '\n'.join(notes)


def run(root: Path = ROOT, *, repeats: int = 3, observe_ms: int = 50) -> dict:
    if not 1 <= repeats <= 10:
        raise ValueError('repeats must be 1..10')
    if not 10 <= observe_ms <= 2000:
        raise ValueError('observe_ms must be 10..2000')
    assert_day11_lock(root)
    plan, stats = load_plans(root)
    bundles = get_source_bundles(root)
    runner = root / RUNNER
    records = []
    request = {**plan, 'observe_ms': observe_ms}
    for repeat in range(1, repeats + 1):
        for revision, bundle in bundles.items():
            result = invoke_node(runner, bundle, request)
            records.extend({'repeat': repeat, 'revision': revision, **row} for row in result)
    analysis = analyze(records, plan['plans'], repeats)
    cross_check = compare_day18(root, records, observe_ms)
    report = {'evidence_level': NOTE, 'generated_utc': datetime.now(timezone.utc).isoformat(),
              'schema_version': SCHEMA, 'target_id': TARGET,
              'plans': plan['plans'], 'plan_stats': stats, 'plans_sha256': sha(root / PLANS),
              'runner_sha256': sha(runner), 'repeats': repeats, 'observe_ms': observe_ms,
              'records': records, 'analysis': analysis, 'day18_check': cross_check}
    output = root / 'results'
    output.mkdir(exist_ok=True)
    (output / 'day19_timing_observations.json').write_text(canonical_json(report), encoding='utf-8')
    (output / 'day19_timing_summary.md').write_text(render(report), encoding='utf-8')
    assert_day11_lock(root)
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('validate', 'run'))
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--observe-ms', type=int, default=50)
    args = p.parse_args()
    try:
        if args.command == 'validate':
            plan, stats = load_plans(ROOT)
            print('Validated Day 19 development plans:', stats)
            print('Plan SHA-256:', sha(ROOT / PLANS))
            print('Not a held-out plan; no source execution')
        else:
            report = run(repeats=args.repeats, observe_ms=args.observe_ms)
            print('Executed:', len(report['records']), 'real pinned-source development tests')
            print('Paired observational differences:', len(report['analysis']['paired_differences']))
            print('Day 18 comparable mismatched fields:', len(report['day18_check']['mismatches']))
            print('Saved:', ROOT / 'results/day19_timing_summary.md')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError,
            TypeError, json.JSONDecodeError) as exc:
        p.exit(1, 'Day 19: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
