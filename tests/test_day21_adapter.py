"""Day 21 adapter tests. Fake queue is explicitly NOT a pinned upstream build."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from webstatecheck import day21_adapter as d21
from webstatecheck.day20_budget import make_pack


FAKE_QUEUE_JS = r'''
export default class StandInQueue {
  constructor({concurrency}) {
    if (concurrency !== 1) throw new Error('stand-in only supports concurrency 1');
    this.pending = 0; this.size = 0; this.tasks = []; this.handlers = new Map();
  }
  on(event, handler) { this.handlers.set(event, handler); }
  clear() { this.tasks = []; this.size = 0; }
  add(task, {signal} = {}) {
    return new Promise((resolve, reject) => {
      this.tasks.push({task, signal, resolve, reject});
      this.size += 1;
      this.pump();
    });
  }
  pump() {
    if (this.pending || this.size === 0) return;
    const entry = this.tasks.shift(); this.size -= 1; this.pending = 1;
    let finished = false;
    const finish = (kind, value) => {
      if (finished) return;
      finished = true;
      this.pending = 0;
      if (kind === 'reject') entry.reject(value);
      else entry.resolve(value);
      queueMicrotask(() => this.pump());
    };
    if (entry.signal) {
      entry.signal.addEventListener('abort', () => finish('reject', entry.signal.reason), {once: true});
    }
    try {
      const value = entry.task();
      if (entry.signal?.aborted) finish('reject', entry.signal.reason);
      Promise.resolve(value).then(value => finish('fulfill', value), error => finish('reject', error));
    } catch (error) { finish('reject', error); }
  }
}
'''


def pack(method='random'):
    return make_pack(method, 20261118)


def make_row(method, scenario, revision, rep):
    return {'plan_id': scenario['plan_id'], 'method': method, 'revision': revision,
            'repeat': rep, 'resources': d21.expected_counts(scenario), 'observe_elapsed_ms': 50.1,
            'snapshot': {key: None for key in d21.COMPARE_FIELDS}}


def make_grid(repeats=2):
    packs = {method: pack(method) for method in ('random', 'heuristic')}
    rows = []
    for rep in range(1, repeats + 1):
        for method, obj in packs.items():
            for revision in ('before', 'after'):
                for scenario in obj['scenarios']:
                    rows.append(make_row(method, scenario, revision, rep))
    return packs, rows


@pytest.mark.parametrize('timing,vector', [
    ('callback_sync', (2, 1, 1, 0, 0, 1)),
    ('callback_microtask', (2, 1, 1, 0, 1, 1)),
    ('external_after_submit', (2, 1, 0, 1, 0, 1)),
    ('none', (2, 0, 0, 0, 0, 1)),
])
def test_runtime_effect_expectations(timing, vector):
    scenario = {'abort_timing': timing}
    counts = d21.expected_counts(scenario)
    assert tuple(counts[key] for key in d21.RESOURCE_KEYS) == vector


def test_complete_grid_and_cost_ledger():
    packs, rows = make_grid()
    result = d21.analyze(rows, packs, 2)
    assert result['executions'] == 32
    assert result['revision_observational_differences'] == []
    assert result['repeat_instability'] == []
    for method in ('random', 'heuristic'):
        assert result['actual_resource_totals'][method]['submissions'] == 32
        assert result['actual_resource_totals'][method]['abort_calls'] == 12
    report = {'analysis': result, 'records': rows, 'repeats': 2}
    text = d21.render(report)
    assert 'not a blinded' in text
    assert 'not independently confirmed bugs' in text


def test_missing_execution_rejected():
    packs, rows = make_grid()
    with pytest.raises(ValueError, match='Incomplete'):
        d21.analyze(rows[:-1], packs, 2)


def test_duplicate_execution_rejected():
    packs, rows = make_grid()
    with pytest.raises(ValueError, match='Duplicate'):
        d21.analyze(rows + [copy.deepcopy(rows[0])], packs, 2)


def test_inconsistent_outcome_and_repeat_instability_are_not_conflated():
    packs, rows = make_grid()
    rows[0]['snapshot']['first_status'] = 'pending'
    result = d21.analyze(rows, packs, 2)
    assert result['revision_observational_differences']
    assert result['repeat_instability']


def test_plan_hashes_are_pinned_to_day20_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(d21, 'assert_day11_lock', lambda root: 'test-lock')
    protocol = tmp_path / d21.PROTOCOL
    protocol.parent.mkdir(parents=True)
    protocol.write_text('versioned test proposal', encoding='utf-8')
    folder = tmp_path / d21.CANDIDATES
    folder.mkdir(parents=True)
    for method in ('random', 'heuristic'):
        (folder / f'{method}.json').write_text(d21.canonical_json(pack(method)), encoding='utf-8')
    audit = {'semantic_budget_vectors_equal': True,
             'methods': {method: {'sha256': d21.sha(folder / f'{method}.json'),
                                  'budget': d21.validate_pack(pack(method))}
                         for method in ('random', 'heuristic')},
             'protocol_sha256': d21.sha(protocol)}
    audit_path = tmp_path / d21.AUDIT
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(d21.canonical_json(audit), encoding='utf-8')
    assert set(d21.load_registered_packs(tmp_path)[0]) == {'random', 'heuristic'}
    tampered = folder / 'random.json'
    tampered.write_text(tampered.read_text() + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='changed or missing'):
        d21.load_registered_packs(tmp_path)


def test_reject_invalid_repeats_before_loading_source(tmp_path):
    with pytest.raises(ValueError, match='Repeats'):
        d21.run(tmp_path, repeats=0)
    with pytest.raises(ValueError, match='Repeats'):
        d21.run(tmp_path, repeats=6)


def test_missing_frozen_checkpoint_is_not_success(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        d21.audit(tmp_path)


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is unavailable')
def test_node_adapter_works_with_isolated_stand_in(tmp_path):
    source = tmp_path / 'standin.mjs'
    source.write_text(FAKE_QUEUE_JS, encoding='utf-8')
    runner = Path(__file__).resolve().parents[1] / d21.RUNNER
    for method in ('random', 'heuristic'):
        scenarios = pack(method)
        rows, wall_ms = d21.invoke_node(runner, source, scenarios)
        assert wall_ms >= 0
        assert len(rows) == 4
        for row, plan in zip(rows, scenarios['scenarios']):
            assert row['resources'] == d21.expected_counts(plan)
            assert row['cleanup'] == 'finished'
            assert row['observe_elapsed_ms'] >= 40
            assert row['snapshot']['first_started'] is True
            assert row['snapshot']['signal_aborted'] == (plan['abort_timing'] != 'none')


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is unavailable')
def test_node_adapter_rejects_unsupported_packet(tmp_path):
    source = tmp_path / 'standin.mjs'
    source.write_text(FAKE_QUEUE_JS, encoding='utf-8')
    packet = pack('random')
    packet['schema_version'] = 'wrong'
    runner = Path(__file__).resolve().parents[1] / d21.RUNNER
    with pytest.raises(RuntimeError, match='Node adapter failed'):
        d21.invoke_node(runner, source, packet)

@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is unavailable')
def test_complete_run_pipeline_with_stand_in_not_real_source(tmp_path, monkeypatch):
    """Exercises report writing end-to-end; NOT an upstream p-queue verification."""
    source = tmp_path / 'standin.mjs'
    source.write_text(FAKE_QUEUE_JS, encoding='utf-8')
    runner = tmp_path / d21.RUNNER
    runner.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[1] / d21.RUNNER, runner)
    monkeypatch.setattr(d21, 'assert_day11_lock', lambda root: 'fake-lock')
    packs = {method: pack(method) for method in ('random', 'heuristic')}
    monkeypatch.setattr(d21, 'load_registered_packs', lambda root: (packs, {m: 'test-hash' for m in packs}))
    monkeypatch.setattr(d21, 'get_source_bundles', lambda root: {'before': source, 'after': source})
    report = d21.run(tmp_path, repeats=1)
    assert report['analysis']['executions'] == 16
    assert report['analysis']['revision_observational_differences'] == []
    assert report['analysis']['repeat_instability'] == []
    assert (tmp_path / d21.OUTPUT).is_file()
    text = (tmp_path / d21.SUMMARY).read_text(encoding='utf-8')
    assert 'Known p-queue feasibility case' in text
    assert 'not independently confirmed bugs' in text
    assert '32' not in text.split('Total actual pinned-source executions: **')[1].split('**')[0]
