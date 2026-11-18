"""Day 20: domain-scoped scheduling vocabulary and prospective *budget* validation.

Development-methodology only. Generates no LLM output, executes no application,
and makes no held-out or AI-performance claim. The old nine-file lock is read-only.

  python -m webstatecheck.day20_budget prepare --seed 20261118
  python -m webstatecheck.day20_budget audit
  cat results/day20_budget_audit.md
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha

SCHEMA = 'wsc-async-schedule-v2-PROPOSAL'
DOMAIN = 'abortable_promise_queue'
METHODS = ('random', 'heuristic')  # LLM requires a separate, isolated generation context.
TIMINGS = ('callback_sync', 'callback_microtask', 'external_after_submit', 'none')
COMPLETIONS = ('held', 'immediate')
PRESET = {'scenarios': 4, 'submissions_per_scenario': 2,
          'observe_ms_per_scenario': 50, 'timeout_ms_per_scenario': 5000}
CANDIDATES = Path('research/day20_candidates')
PROTOCOL = Path('research/DAY20_BUDGET_PROTOCOL_PROPOSAL.md')
IDENTIFIER = re.compile(r'^[a-z][a-z0-9-]{1,31}$')


def _exact(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f'{label}: expected only {sorted(fields)}')
    return value


def validate_pack(pack: object, *, expected_method: str | None = None) -> dict:
    """Validate syntax, action effects and the full balanced cost vector.

    Identical budgets do not imply equivalent runtime difficulty, oracle quality,
    scenario distributions, or blind test generation.
    """
    obj = _exact(pack, {'schema_version', 'domain', 'method', 'scenarios', 'observation'}, 'pack')
    method = obj['method']
    if method not in METHODS or (expected_method is not None and method != expected_method):
        raise ValueError('Unsupported or mismatched method; LLM plans need separate prospective registration')
    if obj['schema_version'] != SCHEMA or obj['domain'] != DOMAIN:
        raise ValueError('Schema/domain mismatch')
    observe = _exact(obj['observation'], {'snapshot_policy', 'observe_ms', 'timeout_ms'}, 'observation')
    if (observe['snapshot_policy'] != 'passive_after_actions_before_cleanup'
            or type(observe['observe_ms']) is not int or observe['observe_ms'] != PRESET['observe_ms_per_scenario']
            or type(observe['timeout_ms']) is not int or observe['timeout_ms'] != PRESET['timeout_ms_per_scenario']):
        raise ValueError('Observation and timeout budgets must be identical and explicit')
    scenarios = obj['scenarios']
    if not isinstance(scenarios, list) or len(scenarios) != PRESET['scenarios']:
        raise ValueError('Expected exactly four scenarios; no hidden retries or extras')

    ids: set[str] = set()
    timings = Counter()
    completions = Counter()
    for row in scenarios:
        scenario = _exact(row, {'plan_id', 'tasks', 'abort_timing'}, 'scenario')
        pid = scenario['plan_id']
        if not isinstance(pid, str) or not IDENTIFIER.fullmatch(pid) or pid in ids:
            raise ValueError('Invalid or duplicated plan ID')
        ids.add(pid)
        timing = scenario['abort_timing']
        if not isinstance(timing, str) or timing not in TIMINGS:
            raise ValueError('Unsupported timing mode')
        timings[timing] += 1
        tasks = scenario['tasks']
        if not isinstance(tasks, list) or len(tasks) != 2:
            raise ValueError('Exactly two submissions per scenario')
        first = _exact(tasks[0], {'role', 'completion', 'abort_signal'}, 'first task')
        second = _exact(tasks[1], {'role', 'completion', 'abort_signal'}, 'second task')
        if (first['role'] != 'subject' or first['completion'] not in COMPLETIONS
                or type(first['abort_signal']) is not bool or first['abort_signal'] is not True):
            raise ValueError('Invalid first task; an AbortSignal is required')
        if second != {'role': 'progress_probe', 'completion': 'immediate', 'abort_signal': False}:
            raise ValueError('Second task is the fixed progress-control task')
        completions[first['completion']] += 1

    if any(timings[t] != 1 for t in TIMINGS):
        raise ValueError('One scenario per timing stratum is required')
    if completions != {'held': 2, 'immediate': 2}:
        raise ValueError('Exactly two held and two immediate first-task profiles required')

    # Account for mutations that occur inside task callbacks as well as after submission.
    # Microtask scheduling is recorded separately, not treated as zero-cost.
    return {
        'scenarios': len(scenarios),
        'submissions': 2 * len(scenarios),
        'abort_calls': sum(timings[t] for t in TIMINGS if t != 'none'),
        'callback_abort_calls': timings['callback_sync'] + timings['callback_microtask'],
        'external_abort_calls': timings['external_after_submit'],
        'microtask_schedules': timings['callback_microtask'],
        'held_first_tasks': completions['held'],
        'immediate_first_tasks': completions['immediate'],
        'passive_snapshots': len(scenarios),
        'total_observe_window_ms': len(scenarios) * observe['observe_ms'],
        'max_wait_ms_each': observe['timeout_ms'],
        'timing_strata': {t: timings[t] for t in TIMINGS},
    }


def make_pack(method: str, seed: int) -> dict:
    if method not in METHODS or type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('Invalid method or unsigned 32-bit seed')
    timings = list(TIMINGS)
    profiles = ['held', 'held', 'immediate', 'immediate']
    if method == 'random':
        rng = random.Random(seed)
        rng.shuffle(timings)
        rng.shuffle(profiles)
    else:
        # Deterministic illustrative heuristic; informed by known development evidence.
        # It must NOT be presented as a general-purpose or independently frozen baseline.
        timings = ['callback_sync', 'external_after_submit', 'callback_microtask', 'none']
        profiles = ['held', 'held', 'immediate', 'immediate']
    pack = {
        'schema_version': SCHEMA, 'domain': DOMAIN, 'method': method,
        'scenarios': [
            {'plan_id': f'{method[0]}-{i:02d}',
             'tasks': [{'role': 'subject', 'completion': profile, 'abort_signal': True},
                       {'role': 'progress_probe', 'completion': 'immediate', 'abort_signal': False}],
             'abort_timing': timing}
            for i, (timing, profile) in enumerate(zip(timings, profiles), 1)
        ],
        'observation': {'snapshot_policy': 'passive_after_actions_before_cleanup',
                        'observe_ms': PRESET['observe_ms_per_scenario'],
                        'timeout_ms': PRESET['timeout_ms_per_scenario']},
    }
    validate_pack(pack, expected_method=method)
    return pack


def prepare(root: Path = ROOT, seed: int = 20261118) -> dict:
    """Produce deterministic examples; never silently replace existing plan files."""
    assert_day11_lock(root)
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('Seed must be an unsigned 32-bit integer')
    folder = root / CANDIDATES
    generated = {m: canonical_json(make_pack(m, seed)) for m in METHODS}
    # Validate possible conflicting files before writing *any* file.
    conflicts = [m for m, content in generated.items()
                 if (folder / f'{m}.json').exists()
                 and (folder / f'{m}.json').read_text(encoding='utf-8') != content]
    if conflicts:
        raise FileExistsError('Would overwrite existing candidate(s): ' + ', '.join(conflicts)
                             + '. Keep the old plans; use a new evaluation cohort for changes.')
    folder.mkdir(parents=True, exist_ok=True)
    for method, content in generated.items():
        file = folder / f'{method}.json'
        if not file.exists():
            file.write_text(content, encoding='utf-8')
    assert_day11_lock(root)
    return {m: {'path': str(folder / f'{m}.json'), 'sha256': sha(folder / f'{m}.json'),
                'budget': validate_pack(json.loads(generated[m]), expected_method=m)} for m in METHODS}


def audit(root: Path = ROOT) -> dict:
    day11 = assert_day11_lock(root)
    folder = root / CANDIDATES
    details = {}
    for method in METHODS:
        path = folder / f'{method}.json'
        if not path.is_file():
            raise FileNotFoundError(f'{method} pack missing; run Day 20 prepare first')
        packet = json.loads(path.read_text(encoding='utf-8'))
        details[method] = {'sha256': sha(path), 'budget': validate_pack(packet, expected_method=method),
                           'timing_profile_pairs': sorted((s['abort_timing'], s['tasks'][0]['completion'])
                                                          for s in packet['scenarios'])}
    equal = details['random']['budget'] == details['heuristic']['budget']
    if not equal:
        raise ValueError('Unequal semantic budget; no valid comparison packet produced')
    info = {'classification': 'DEVELOPMENT PROPOSAL ONLY — not an actual benchmark',
            'schema': SCHEMA, 'domain': DOMAIN, 'day11_lock_sha256': day11,
            'protocol_sha256': sha(root / PROTOCOL), 'methods': details,
            'semantic_budget_vectors_equal': equal,
            'actual_execution': False, 'llm_generated': False, 'target_registered': False,
            'known_issue_contamination': True}
    lines = ['# Day 20 — Scheduling vocabulary and semantic-budget preflight', '',
             '**Development-only protocol amendment proposal. No application execution, new target, or LLM result.**', '',
             f'Domain: `{DOMAIN}`. Two seeded example methods: random and heuristic.', '',
             '| Resource / scenario group | Random | Heuristic |', '|---|---:|---:|']
    vector = details['random']['budget']
    for key, value in vector.items():
        if key == 'timing_strata':
            for timing in TIMINGS:
                lines.append(f"| Timing stratum `{timing}` | {value[timing]} | {details['heuristic']['budget'][key][timing]} |")
        else:
            lines.append(f"| {key.replace('_',' ')} | {value} | {details['heuristic']['budget'][key]} |")
    lines += ['', f'Budget vectors identical: **{equal}**.', '',
              '## Plan provenance', '',
              f"- Random SHA-256: `{details['random']['sha256']}`",
              f"- Heuristic SHA-256: `{details['heuristic']['sha256']}`",
              f"- Amendment proposal SHA-256: `{info['protocol_sha256']}`", '',
              '## Limits and decisions still needed', '',
              '- The grammar applies to **abortable promise/task queues**, not arbitrary web applications.',
              '- Equal marginal timing/profile counts and mutation vectors do **not** equalize interactions or runtime difficulty.',
              '- Callback-initiated aborts are counted as API mutations; microtask scheduling is separately recorded.',
              '- Observation is passive and has a fixed pre-cleanup window; later adapters must enforce it.',
              '- Plan structure is validated, **not executed**; no v2 target adapter or independently reviewed oracle exists yet.',
              '- Heuristic construction used known development context; no held-out scoring or AI superiority is justified.',
              '- A future model plan must be generated independently, logged, and validated under the exact same schema.',
              '- Total model tokens, generation latency, retries, wall-clock time and unique independent defects are still unmeasured.',
              '- This is a separate proposal; the Day 11 nine-file lock and staged t01 must remain unchanged.', '',
              '**Next:** review schema and implement a target-neutral adapter conformance suite before choosing a new blinded case.', '']
    out = root / 'results'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'day20_budget_audit.json').write_text(canonical_json(info), encoding='utf-8')
    (out / 'day20_budget_audit.md').write_text('\n'.join(lines), encoding='utf-8')
    assert_day11_lock(root)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'audit'))
    parser.add_argument('--seed', type=int, default=20261118)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            output = prepare(seed=args.seed)
            print('Prepared two development-only plan packs:')
            print(canonical_json(output).strip())
        else:
            info = audit()
            print('Semantic budget vectors equal:', info['semantic_budget_vectors_equal'])
            print('Application executions: 0; LLM plans generated: 0; independent targets: 0')
            print('Saved:', ROOT / 'results/day20_budget_audit.md')
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(1, 'Day 20: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
