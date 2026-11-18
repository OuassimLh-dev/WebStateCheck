"""Day 22: audit pairing confounds and run an eight-cell development factorial.

No LLM generation, target registration, held-out testing, or modification of
Day 11 locked files / Day 20 registered candidate packs.

  python -m webstatecheck.day22_pairing audit
  python -m webstatecheck.day22_pairing prepare
  python -m webstatecheck.day22_pairing run --repeats 2
"""
from __future__ import annotations

import argparse
import copy
import json
from hashlib import sha256
from collections import Counter, defaultdict
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha
from webstatecheck.day18_gap_diagnostic import get_source_bundles
from webstatecheck.day20_budget import TIMINGS, COMPLETIONS, validate_pack
from webstatecheck import day21_adapter as d21

FOLDER = Path('research/day22_development')
MANIFEST = FOLDER / 'manifest.json'
AUDIT_MD = Path('results/day22_pairing_audit.md')
FACTORIAL_MD = Path('results/day22_factorial_summary.md')
FACTORIAL_JSON = Path('results/day22_factorial_observations.json')
FOLDS = ('fold_a', 'fold_b')


def cell(scenario: dict) -> tuple[str, str]:
    return scenario['abort_timing'], scenario['tasks'][0]['completion']


def read_day21(root: Path = ROOT) -> tuple[dict, dict, dict]:
    """Check provenance and recompute the saved Day 21 analysis; never invent outcomes."""
    packs, hashes = d21.load_registered_packs(root)
    file = root / d21.OUTPUT
    if not file.is_file():
        raise FileNotFoundError('Day 21 observations missing; run day21_adapter run first')
    report = json.loads(file.read_text(encoding='utf-8'))
    if report.get('plan_sha256') != hashes or report.get('runner_sha256') != sha(root / d21.RUNNER):
        raise ValueError('Day 21 plan/runner provenance mismatch')
    if report.get('heldout') is not False or report.get('llm_generated') is not False:
        raise ValueError('Day 21 report classification mismatch')
    repeats, rows = report.get('repeats'), report.get('records')
    if type(repeats) is not int or not 1 <= repeats <= 5 or not isinstance(rows, list):
        raise ValueError('Day 21 execution grid malformed')
    for row in rows:
        pack = packs.get(row.get('method'))
        if pack is None:
            raise ValueError('Unknown Day 21 method in observations')
        scenario = next((s for s in pack['scenarios'] if s['plan_id'] == row.get('plan_id')), None)
        if scenario is None or cell(row_to_scenario(row)) != cell(scenario):
            raise ValueError('Day 21 row does not match plan dimensions')
        if row.get('resources') != d21.expected_counts(scenario) or row.get('cleanup') != 'finished':
            raise ValueError('Day 21 recorded resource/cleanup mismatch')
    recomputed = d21.analyze(rows, packs, repeats)
    if recomputed != report.get('analysis'):
        raise ValueError('Day 21 saved analysis disagrees with recomputation')
    return report, packs, hashes


def row_to_scenario(row: dict) -> dict:
    return {'abort_timing': row.get('abort_timing'),
            'tasks': [{'completion': row.get('subject_completion')}]}


def pairing_table(packs: dict) -> dict:
    table = {f'{timing}/{profile}': [] for timing in TIMINGS for profile in COMPLETIONS}
    for method, pack in packs.items():
        for scenario in pack['scenarios']:
            table['/'.join(cell(scenario))].append({'method': method, 'plan_id': scenario['plan_id']})
    return table


def audit(root: Path = ROOT) -> dict:
    report, packs, hashes = read_day21(root)
    analysis = report['analysis']
    changes = analysis['revision_observational_differences']
    unique_cells = set()
    for changed in changes:
        match = next(s for s in packs[changed['method']]['scenarios'] if s['plan_id'] == changed['plan_id'])
        unique_cells.add(cell(match))
    table = pairing_table(packs)
    output = {'day21_report_sha256': sha(root / d21.OUTPUT),
              'day21_plan_sha256': hashes,
              'repeats': report['repeats'],
              'pairing_table': table,
              'changed_execution_pairs': len(changes),
              'changed_unique_scenarios': len({(c['method'], c['plan_id']) for c in changes}),
              'changed_unique_cells': [list(c) for c in sorted(unique_cells)],
              'overlapping_cells': [key for key, vals in table.items() if len(vals) > 1],
              'uncovered_cells': [key for key, vals in table.items() if not vals],
              'label': 'development confounding audit; not defect scoring'}
    lines = ['# Day 22 — Day 21 timing/profile pairing audit', '',
             '**Retrospective development audit. NOT AI testing, blinded evaluation or new defect discovery.**', '',
             f"Revalidated saved Day 21 report and its plan/runner hashes; **{report['repeats']}** repeats.", '',
             '| Timing stratum | Held-profile method(s) | Immediate-profile method(s) |',
             '|---|---|---|']
    for timing in TIMINGS:
        texts = []
        for profile in COMPLETIONS:
            entries = table[f'{timing}/{profile}']
            texts.append(', '.join(x['method'] for x in entries) or '—')
        lines.append(f'| `{timing}` | {texts[0]} | {texts[1]} |')
    lines.extend(['', f"Saved before/after changed execution pairs: **{len(changes)}**.",
                  f"Distinct plans with changes: **{output['changed_unique_scenarios']}**.",
                  f"Distinct timing/profile cells with changes: **{len(unique_cells)}**.",
                  f"Cells covered by both methods: **{len(output['overlapping_cells'])}/8**.",
                  f"Cells missing from both methods: **{len(output['uncovered_cells'])}/8**.", '',
                  'These counts are not unique confirmed bugs; identical profiles and timing can be repeated across runs.',
                  'Equal resource totals do not remove confounding from the timing/profile pairing.',
                  'Next: run the full 2 × 4 timing/profile matrix once per revision/repeat using the same instrumented adapter.',
                  'Do not seal `t01`; leave all nine frozen Day 11 files unchanged.', ''])
    (root / AUDIT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / AUDIT_MD).write_text('\n'.join(lines), encoding='utf-8')
    assert_day11_lock(root)
    return output


def make_folds(root: Path = ROOT) -> dict:
    """The first fold uses existing random pairings; the second is its complement."""
    _, packs, hashes = read_day21(root)
    reference = packs['random']
    folds = {}
    for fold_id, toggle in [('fold_a', False), ('fold_b', True)]:
        pack = copy.deepcopy(reference)
        # technical method field is 'random' for compatibility with frozen Day 21 runner;
        # these folds are NOT random-vs-heuristic strategy competitors.
        for i, scenario in enumerate(pack['scenarios'], 1):
            scenario['plan_id'] = f"{fold_id.replace('_', '-')}-{i:02d}"
            if toggle:
                previous = scenario['tasks'][0]['completion']
                scenario['tasks'][0]['completion'] = 'immediate' if previous == 'held' else 'held'
        validate_pack(pack, expected_method='random')
        folds[fold_id] = pack
    coverage = Counter(cell(s) for pack in folds.values() for s in pack['scenarios'])
    if len(coverage) != 8 or any(count != 1 for count in coverage.values()):
        raise ValueError('Factorial folds do not cover each cell exactly once')
    return {'folds': folds, 'reference_hashes': hashes,
            'day21_runner_sha256': sha(root / d21.RUNNER),
            'day21_report_sha256': sha(root / d21.OUTPUT)}


def prepare(root: Path = ROOT) -> dict:
    assert_day11_lock(root)
    material = make_folds(root)
    folder = root / FOLDER
    files = {fold: canonical_json(pack) for fold, pack in material['folds'].items()}
    hashes = {fold: sha256(data.encode('utf-8')).hexdigest()
              for fold, data in files.items()}
    manifest = {'purpose': 'Day 22 development factorial, not held-out scoring',
                'plan_sha256': hashes, 'source_day20_plan_sha256': material['reference_hashes'],
                'day21_runner_sha256': material['day21_runner_sha256'],
                'day21_report_sha256': material['day21_report_sha256'],
                'cells': 8, 'frozen_protocol_modified': False}
    contents = {**{f'{fold}.json': text for fold, text in files.items()},
                'manifest.json': canonical_json(manifest)}
    for name, content in contents.items():
        path = folder / name
        if path.exists() and path.read_text(encoding='utf-8') != content:
            raise FileExistsError(f'Would overwrite changed development packet: {path}')
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        path = folder / name
        if not path.exists():
            path.write_text(content, encoding='utf-8')
    assert_day11_lock(root)
    return manifest


def load_folds(root: Path = ROOT) -> tuple[dict, dict]:
    current = make_folds(root)
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError('Day 22 manifest missing; run prepare first')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (manifest.get('source_day20_plan_sha256') != current['reference_hashes']
            or manifest.get('day21_runner_sha256') != current['day21_runner_sha256']
            or manifest.get('day21_report_sha256') != current['day21_report_sha256']):
        raise ValueError('Day 22 source inputs changed after preparation')
    folds = {}
    for fold in FOLDS:
        path = root / FOLDER / f'{fold}.json'
        if not path.is_file() or manifest['plan_sha256'].get(fold) != sha(path):
            raise ValueError(f'Day 22 {fold} plan missing or hash mismatch')
        pack = json.loads(path.read_text(encoding='utf-8'))
        validate_pack(pack, expected_method='random')
        if pack != current['folds'][fold]:
            raise ValueError('Development fold does not match prepared factorial')
        folds[fold] = pack
    return folds, manifest


def analyze_factorial(records: list[dict], folds: dict, repeats: int) -> dict:
    lookup = {}
    for row in records:
        key = row['repeat'], row['fold'], row['revision'], row['plan_id']
        if key in lookup:
            raise ValueError('Duplicate factorial execution')
        lookup[key] = row
    expected = {(rep, fold, revision, scenario['plan_id'])
                for rep in range(1, repeats + 1) for fold, pack in folds.items()
                for revision in ('before', 'after') for scenario in pack['scenarios']}
    if set(lookup) != expected:
        raise ValueError('Incomplete factorial execution grid')
    # Independently recheck the actual resource ledger, even if caller bypasses
    # the stricter Day 21 node-response validator.
    scenarios_by_fold = {fold: {s['plan_id']: s for s in pack['scenarios']}
                         for fold, pack in folds.items()}
    for row in records:
        scenario = scenarios_by_fold[row['fold']][row['plan_id']]
        if (row.get('resources') != d21.expected_counts(scenario)
                or row.get('cleanup') != 'finished'):
            raise ValueError('Factorial execution resource/cleanup mismatch')
        if (row.get('abort_timing') != scenario['abort_timing']
                or row.get('subject_completion') != scenario['tasks'][0]['completion']):
            raise ValueError('Factorial scenario dimension mismatch')
        if (not isinstance(row.get('snapshot'), dict)
                or set(row['snapshot']) != set(d21.COMPARE_FIELDS)):
            raise ValueError('Factorial snapshot schema mismatch')
    cells = {}
    changed_pairs = 0
    instability = []
    for fold, pack in folds.items():
        for scenario in pack['scenarios']:
            label = '/'.join(cell(scenario))
            per_repeat = []
            for rep in range(1, repeats + 1):
                before = lookup[(rep, fold, 'before', scenario['plan_id'])]['snapshot']
                after = lookup[(rep, fold, 'after', scenario['plan_id'])]['snapshot']
                diffs = [key for key in d21.COMPARE_FIELDS if before[key] != after[key]]
                changed_pairs += bool(diffs)
                per_repeat.append({'repeat': rep, 'before_first': before['first_status'],
                                   'after_first': after['first_status'],
                                   'before_next_started': before['second_started'],
                                   'after_next_started': after['second_started'],
                                   'different_fields': diffs})
            for revision in ('before', 'after'):
                first = lookup[(1, fold, revision, scenario['plan_id'])]['snapshot']
                if any(first != lookup[(rep, fold, revision, scenario['plan_id'])]['snapshot']
                       for rep in range(2, repeats + 1)):
                    instability.append({'cell': label, 'revision': revision})
            if label in cells:
                raise ValueError('Duplicate factorial cell')
            cells[label] = {'fold': fold, 'plan_id': scenario['plan_id'], 'trials': per_repeat,
                            'changed_repeat_count': sum(bool(v['different_fields']) for v in per_repeat)}
    if len(cells) != 8:
        raise ValueError('Full timing/profile design not achieved')
    resources = {fold: Counter() for fold in folds}
    for row in records:
        resources[row['fold']].update(row['resources'])
    if resources['fold_a'] != resources['fold_b']:
        raise ValueError('Actual executed budget differs between factorial folds')
    return {'executions': len(records), 'repeat_count': repeats, 'cells': cells,
            'changed_paired_executions': changed_pairs,
            'changed_cells': sorted(k for k, info in cells.items() if info['changed_repeat_count']),
            'repeat_instability': instability,
            'resource_totals': {fold: dict(counts) for fold, counts in resources.items()}}


def render_factorial(info: dict) -> str:
    lines = ['# Day 22 — Timing × task-profile factorial diagnostic', '',
             '**Development-only, known p-queue source/fix case. No AI plan, held-out benchmark, or newly discovered defect.**', '',
             f"Real pinned-source executions: **{info['executions']}**; repeats per cell/revision: **{info['repeat_count']}**.",
             'All eight cells of the 4 timing × 2 task-profile design were exercised.', '',
             '| Cancellation timing | Task profile | Old first / next started | Fixed first / next started | Changed pairs |',
             '|---|---|---|---|---:|']
    for timing in TIMINGS:
        for profile in COMPLETIONS:
            row = info['cells'][f'{timing}/{profile}']
            sample = row['trials'][0]
            lines.append(f"| `{timing}` | `{profile}` | {sample['before_first']} / {sample['before_next_started']} | "
                         f"{sample['after_first']} / {sample['after_next_started']} | {row['changed_repeat_count']} |")
    lines += ['', f"Revision-paired observations with any difference: **{info['changed_paired_executions']}**.",
              f"Different cells: **{len(info['changed_cells'])}/8**.",
              f"Within-revision repeat instability: **{len(info['repeat_instability'])}**.",
              'Actual resource totals are equal between the two complementary folds: **True**.', '',
              '## Interpretation', '',
              '- This experiment separates timing from task completion profile to expose pairing effects.',
              '- The folds are **diagnostic cells**, not competing random/heuristic/LLM methods.',
              '- An observable before/after difference is a diagnostic lead, not an independently adjudicated bug.',
              '- Existing Day 20 method plans and Day 11 locked files remain unchanged; `t01` is unsealed.',
              '- The runner and source-pinned case are already informed by the historical issue and are not blinded.',
              '- The next prospective study needs independently selected targets, external contract/oracle review and isolated model prompting.', '']
    return '\n'.join(lines)


def run(root: Path = ROOT, repeats: int = 2) -> dict:
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError('Repeats must be an integer between 1 and 5')
    assert_day11_lock(root)
    folds, manifest = load_folds(root)
    bundles = get_source_bundles(root)
    runner = root / d21.RUNNER
    rows = []
    for rep in range(1, repeats + 1):
        for fold, pack in folds.items():
            for revision, bundle in bundles.items():
                executions, _ = d21.invoke_node(runner, bundle, pack)
                for item in executions:
                    rows.append({**item, 'fold': fold, 'revision': revision, 'repeat': rep})
    info = analyze_factorial(rows, folds, repeats)
    report = {'classification': 'DAY22 DEVELOPMENT FACTORIAL, NOT HOLDOUT',
              'plan_sha256': manifest['plan_sha256'], 'runner_sha256': sha(runner),
              'repeats': repeats, 'records': rows, 'analysis': info,
              'heldout': False, 'llm_generated': False}
    assert_day11_lock(root)
    (root / FACTORIAL_JSON).parent.mkdir(parents=True, exist_ok=True)
    (root / FACTORIAL_JSON).write_text(canonical_json(report), encoding='utf-8')
    (root / FACTORIAL_MD).write_text(render_factorial(info), encoding='utf-8')
    assert_day11_lock(root)
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('audit', 'prepare', 'run'))
    p.add_argument('--repeats', type=int, default=2)
    args = p.parse_args()
    try:
        if args.command == 'audit':
            info = audit()
            print('Day 21 timing/profile cells:', 8 - len(info['uncovered_cells']), 'of 8')
            print('Changed Day 21 execution pairs:', info['changed_execution_pairs'])
            print('Changed unique cells:', info['changed_unique_cells'])
            print('Saved:', ROOT / AUDIT_MD)
        elif args.command == 'prepare':
            info = prepare()
            print('Prepared two complementary development folds:', info['plan_sha256'])
            print('No application execution or AI plan generation')
        else:
            info = run(repeats=args.repeats)['analysis']
            print('Actual pinned-source executions:', info['executions'])
            print('Changed timing/profile cells:', info['changed_cells'])
            print('Repeat instability:', len(info['repeat_instability']))
            print('Saved:', ROOT / FACTORIAL_MD)
    except (OSError, KeyError, ValueError, TypeError, RuntimeError, json.JSONDecodeError) as exc:
        p.exit(1, 'Day 22: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
