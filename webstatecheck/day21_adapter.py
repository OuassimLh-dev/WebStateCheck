"""Day 21: verify actual adapter mutations against Day 20 proposed semantic budgets.

Development-only. Runs known p-queue source pairs on the user's Mac but does not
score historical defects, run an LLM, register a holdout, or alter frozen files.

Usage:
  python -m webstatecheck.day21_adapter audit
  python -m webstatecheck.day21_adapter run --repeats 2
  cat results/day21_adapter_summary.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha
from webstatecheck.day18_gap_diagnostic import get_source_bundles
from webstatecheck.day20_budget import CANDIDATES, METHODS, TIMINGS, PROTOCOL, validate_pack

RUNNER = Path('realworld/p_queue_holdout/day21_adapter_runner.mjs')
OUTPUT = Path('results/day21_adapter_observations.json')
SUMMARY = Path('results/day21_adapter_summary.md')
AUDIT = Path('results/day20_budget_audit.json')
RESOURCE_KEYS = ('submissions', 'abort_calls', 'callback_abort_calls',
                 'external_abort_calls', 'microtask_schedules', 'passive_snapshots')
COMPARE_FIELDS = ('first_started', 'first_status', 'first_error', 'second_started',
                  'second_status', 'signal_aborted', 'queue_pending', 'queue_size',
                  'queue_error_events', 'events_before_snapshot')


def expected_counts(scenario: dict) -> dict:
    mode = scenario['abort_timing']
    return {'submissions': 2, 'abort_calls': int(mode != 'none'),
            'callback_abort_calls': int(mode in ('callback_sync', 'callback_microtask')),
            'external_abort_calls': int(mode == 'external_after_submit'),
            'microtask_schedules': int(mode == 'callback_microtask'),
            'passive_snapshots': 1}


def load_registered_packs(root: Path = ROOT) -> tuple[dict, dict]:
    """Reject changed plans since Day 20 audit, even when still schema-valid."""
    assert_day11_lock(root)
    prior_path = root / AUDIT
    if not prior_path.is_file():
        raise FileNotFoundError('Missing Day 20 audit; rerun day20_budget audit')
    prior = json.loads(prior_path.read_text(encoding='utf-8'))
    if prior.get('semantic_budget_vectors_equal') is not True or not isinstance(prior.get('methods'), dict):
        raise ValueError('Day 20 resource audit did not pass')
    if prior.get('protocol_sha256') != sha(root / PROTOCOL):
        raise ValueError('Day 20 protocol proposal changed since audit')
    packs = {}
    budget = {}
    for method in METHODS:
        candidate = root / CANDIDATES / f'{method}.json'
        if not candidate.is_file() or prior['methods'].get(method, {}).get('sha256') != sha(candidate):
            raise ValueError(f'Day 20 {method} candidate changed or missing since audit')
        packet = json.loads(candidate.read_text(encoding='utf-8'))
        budget[method] = validate_pack(packet, expected_method=method)
        if budget[method] != prior['methods'][method]['budget']:
            raise ValueError('Candidate cost vector changed')
        packs[method] = packet
    if budget['random'] != budget['heuristic']:
        raise ValueError('Cost vectors differ')
    return packs, {method: sha(root / CANDIDATES / f'{method}.json') for method in METHODS}


def audit(root: Path = ROOT) -> dict:
    packs, plan_hashes = load_registered_packs(root)
    expected = {method: dict(Counter(k for row in pack['scenarios']
                         for k, amount in expected_counts(row).items() for _ in range(amount)))
                for method, pack in packs.items()}
    for method in METHODS:
        for key in RESOURCE_KEYS:
            expected[method].setdefault(key, 0)
    if expected['random'] != expected['heuristic']:
        raise ValueError('Declared instrumentable resource totals differ')
    return {'plan_sha256': plan_hashes, 'expected_runtime_resources': expected,
            'verified_day11': True, 'execution': False,
            'development_only': True}


def invoke_node(runner: Path, bundle: Path, pack: dict) -> tuple[list[dict], float]:
    start = time.monotonic()
    try:
        proc = subprocess.run(['node', str(runner), str(bundle)], input=canonical_json(pack),
                              capture_output=True, text=True, timeout=45, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Node adapter exceeded process timeout; no valid conformance result') from exc
    elapsed_ms = (time.monotonic() - start) * 1000
    if proc.returncode:
        raise RuntimeError('Node adapter failed: ' + proc.stderr[-2200:])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Node adapter did not return a JSON payload') from exc
    if data.get('schema_version') != pack['schema_version'] or data.get('method') != pack['method']:
        raise ValueError('Adapter response contains inconsistent schema or method')
    rows = data.get('records')
    if not isinstance(rows, list) or len(rows) != len(pack['scenarios']):
        raise ValueError('Missing or extra scenario executions')
    if [row.get('plan_id') for row in rows] != [s['plan_id'] for s in pack['scenarios']]:
        raise ValueError('Unexpected response scenario IDs or order')
    for row, scenario in zip(rows, pack['scenarios']):
        if row.get('abort_timing') != scenario['abort_timing'] or row.get('subject_completion') != scenario['tasks'][0]['completion']:
            raise ValueError('Returned scenario dimensions do not match plan')
        actual = row.get('resources')
        expected = expected_counts(scenario)
        if not isinstance(actual, dict) or set(actual) != set(RESOURCE_KEYS) or any(
                type(actual[k]) is not int or actual[k] != expected[k] for k in RESOURCE_KEYS):
            raise ValueError(f'Instrumented operation accounting mismatch for {row["plan_id"]}')
        snapshot = row.get('snapshot')
        if not isinstance(snapshot, dict) or set(snapshot) != set(COMPARE_FIELDS):
            raise ValueError('Missing observed pre-cleanup fields')
        for key in ('first_started', 'second_started', 'signal_aborted'):
            if type(snapshot[key]) is not bool:
                raise ValueError('Invalid snapshot bool')
        for key in ('first_status', 'second_status'):
            if snapshot[key] not in ('pending', 'fulfilled', 'rejected'):
                raise ValueError('Invalid task completion status')
        if not isinstance(row.get('observe_elapsed_ms'), (int, float)) or row['observe_elapsed_ms'] < 0:
            raise ValueError('Invalid measured observation time')
        if row.get('cleanup') != 'finished':
            raise ValueError('Post-observation cleanup failed; report cannot be scored')
    return rows, round(elapsed_ms, 3)


def analyze(records: list[dict], packs: dict, repeats: int) -> dict:
    lookup = {}
    for row in records:
        key = row['repeat'], row['method'], row['revision'], row['plan_id']
        if key in lookup:
            raise ValueError('Duplicate recorded execution')
        lookup[key] = row
    expected = {(rep, method, revision, scenario['plan_id'])
                for rep in range(1, repeats + 1) for method, pack in packs.items()
                for revision in ('before', 'after') for scenario in pack['scenarios']}
    if set(lookup) != expected:
        raise ValueError('Incomplete execution grid')
    resource_totals = {method: Counter() for method in METHODS}
    elapsed = {method: [] for method in METHODS}
    for row in records:
        resource_totals[row['method']].update(row['resources'])
        elapsed[row['method']].append(row['observe_elapsed_ms'])
    paired_changes = []
    instability = []
    for method, pack in packs.items():
        for scenario in pack['scenarios']:
            pid = scenario['plan_id']
            for rep in range(1, repeats + 1):
                old = lookup[(rep, method, 'before', pid)]['snapshot']
                new = lookup[(rep, method, 'after', pid)]['snapshot']
                different = [key for key in COMPARE_FIELDS if old[key] != new[key]]
                if different:
                    paired_changes.append({'repeat': rep, 'method': method, 'plan_id': pid, 'fields': different})
            for revision in ('before', 'after'):
                snap = lookup[(1, method, revision, pid)]['snapshot']
                if any(lookup[(rep, method, revision, pid)]['snapshot'] != snap
                       for rep in range(2, repeats + 1)):
                    instability.append({'method': method, 'revision': revision, 'plan_id': pid})
    return {'executions': len(records), 'actual_resource_totals': {k: dict(v) for k, v in resource_totals.items()},
            'mean_observe_ms_by_method': {k: round(sum(v) / len(v), 3) for k, v in elapsed.items()},
            'revision_observational_differences': paired_changes,
            'repeat_instability': instability}


def render(report: dict) -> str:
    info = report['analysis']
    lines = ['# Day 21 — Executed resource-accounting conformance (development)', '',
             '**Known p-queue feasibility case; not a blinded evaluation, independent defect discovery, or LLM comparison.**', '',
             f"Plan files match their Day 20 audited hashes. Day 11 lock verified. Repeats per plan/revision: **{report['repeats']}**.",
             f"Total actual pinned-source executions: **{info['executions']}**.", '',
             '| Method | Executions | Submissions | Abort calls | Callback abort | External abort | Microtasks | Passive snapshots |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for method in METHODS:
        totals = info['actual_resource_totals'][method]
        lines.append(f"| {method} | {sum(1 for r in report['records'] if r['method'] == method)} | "
                     + ' | '.join(str(totals[k]) for k in RESOURCE_KEYS) + ' |')
    lines += ['', f"Paired before/after observational differences: **{len(info['revision_observational_differences'])}** (not independently confirmed bugs).",
              f"Within-revision repeat instability: **{len(info['repeat_instability'])}**.",
              'Measured mean passive observation delays (ms): ' + ', '.join(
                  f"{m} = {info['mean_observe_ms_by_method'][m]}" for m in METHODS) + '.', '',
              '## Scope and limitations', '',
              '- JS counters measure actual queue submissions, AbortController calls, microtask scheduling and snapshots for each scenario.',
              '- Snapshot fields are recorded before releasing delayed gates; cleanup success is checked separately.',
              '- The same runnable adapter and source-pinned bundles are used for both methods and revisions.',
              '- Each method is forced to use all four timing strata once; it primarily chooses how to pair timing with task profiles. This severely narrows what a strategy can discover.',
              '- The four profile/timing pairings can differ even when marginal budgets match; matching costs is necessary but insufficient for fair effectiveness comparisons.',
              '- Timing accuracy is observed, not experimentally controlled beyond a nominal timer window.',
              '- `p-queue` is a known development case in this conversation. We deliberately do NOT score success against its historical bug.',
              '- This does not establish correctness of domain oracles, AI effectiveness, unique defects, or generalization.',
              '- Future genuinely independent studies require an isolated model generation context, an independently approved oracle, and a separately preregistered v2 cohort.',
              '- No frozen Day 11 file or staged t01 registration is modified.', '']
    return '\n'.join(lines)


def run(root: Path = ROOT, repeats: int = 2) -> dict:
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError('Repeats must be 1 to 5')
    packs, hashes = load_registered_packs(root)
    bundles = get_source_bundles(root)
    runner = root / RUNNER
    if not runner.is_file():
        raise FileNotFoundError('Day 21 adapter JS missing; reinstall add-on')
    records = []
    invocations = []
    for rep in range(1, repeats + 1):
        for method in METHODS:
            pack = packs[method]
            for revision, bundle in bundles.items():
                rows, wall_ms = invoke_node(runner, bundle, pack)
                invocations.append({'repeat': rep, 'method': method,
                                    'revision': revision, 'node_wall_ms': wall_ms})
                for row in rows:
                    records.append({**row, 'repeat': rep, 'revision': revision, 'method': method})
    info = analyze(records, packs, repeats)
    report = {'classification': 'DEVELOPMENT-ONLY ADAPTER CONFORMANCE',
              'plan_sha256': hashes, 'runner_sha256': sha(runner),
              'repeats': repeats, 'records': records, 'invocations': invocations,
              'analysis': info, 'heldout': False, 'llm_generated': False}
    assert_day11_lock(root)
    path = root / OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(report), encoding='utf-8')
    (root / SUMMARY).write_text(render(report), encoding='utf-8')
    assert_day11_lock(root)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('audit', 'run'))
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            report = audit()
            print('Audited Day 20 plan hashes; expected runtime resource totals:')
            print(canonical_json(report['expected_runtime_resources']).strip())
            print('No source execution in audit mode')
        else:
            report = run(repeats=args.repeats)
            print('Real pinned-source executions:', report['analysis']['executions'])
            print('Observed revision differences:', len(report['analysis']['revision_observational_differences']))
            print('Repeat instability:', len(report['analysis']['repeat_instability']))
            print('Saved:', ROOT / SUMMARY)
    except (OSError, KeyError, ValueError, RuntimeError, TypeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        parser.exit(1, 'Day 21: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
