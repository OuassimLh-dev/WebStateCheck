"""Day 22 is a diagnostic; stand-in queue tests do NOT validate real p-queue."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from webstatecheck import day22_pairing as d22
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
      finished = true; this.pending = 0;
      if (kind === 'reject') entry.reject(value);
      else entry.resolve(value);
      queueMicrotask(() => this.pump());
    };
    if (entry.signal) entry.signal.addEventListener('abort', () => finish('reject', entry.signal.reason), {once:true});
    try {
      const value = entry.task();
      if (entry.signal?.aborted) finish('reject', entry.signal.reason);
      Promise.resolve(value).then(value => finish('fulfill', value), error => finish('reject', error));
    } catch (error) { finish('reject', error); }
  }
}
'''


def fake_day21(root: Path):
    packs = {name: make_pack(name, 20261118) for name in ('random', 'heuristic')}
    report = {'repeats': 2, 'analysis': {
        'revision_observational_differences': [
            {'repeat': 1, 'method': 'heuristic', 'plan_id': 'h-01', 'fields': ['first_status']},
            {'repeat': 2, 'method': 'heuristic', 'plan_id': 'h-01', 'fields': ['first_status']},
        ]}}
    return report, packs, {'random': 'random-hash', 'heuristic': 'heuristic-hash'}


def setup_development_folder(tmp_path, monkeypatch):
    runner = tmp_path / d21.RUNNER
    runner.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[1] / d21.RUNNER, runner)
    observations = tmp_path / d21.OUTPUT
    observations.parent.mkdir(parents=True)
    observations.write_text('{"test":true}', encoding='utf-8')
    monkeypatch.setattr(d22, 'read_day21', lambda root: fake_day21(root))
    monkeypatch.setattr(d22, 'assert_day11_lock', lambda root: 'dummy-lock')
    return runner


def test_pair_table_is_not_automatically_balanced():
    _, packs, _ = fake_day21(Path('.'))
    table = d22.pairing_table(packs)
    assert len(table) == 8
    assert sum(len(entries) for entries in table.values()) == 8
    assert any(not entries for entries in table.values())


def test_day21_paired_differences_are_one_unique_cell(tmp_path, monkeypatch):
    setup_development_folder(tmp_path, monkeypatch)
    output = d22.audit(tmp_path)
    assert output['changed_execution_pairs'] == 2
    assert output['changed_unique_scenarios'] == 1
    assert output['changed_unique_cells'] == [['callback_sync', 'held']]
    text = (tmp_path / d22.AUDIT_MD).read_text()
    assert 'Distinct timing/profile cells with changes: **1**' in text
    assert 'NOT AI testing' in text


def test_pairing_folds_cover_all_eight_cells(tmp_path, monkeypatch):
    setup_development_folder(tmp_path, monkeypatch)
    material = d22.make_folds(tmp_path)
    folds = material['folds']
    assert len(folds) == 2
    assert all(pack['method'] == 'random' for pack in folds.values())
    cells = [d22.cell(s) for pack in folds.values() for s in pack['scenarios']]
    assert len(set(cells)) == 8
    assert len(cells) == 8


def test_prepare_does_not_overwrite_modified_pack(tmp_path, monkeypatch):
    setup_development_folder(tmp_path, monkeypatch)
    first = d22.prepare(tmp_path)
    assert first == d22.prepare(tmp_path)
    folds, _ = d22.load_folds(tmp_path)
    assert set(folds) == set(d22.FOLDS)
    tampered = tmp_path / d22.FOLDER / 'fold_b.json'
    tampered.write_text(tampered.read_text() + '\n')
    with pytest.raises(FileExistsError, match='Would overwrite'):
        d22.prepare(tmp_path)
    with pytest.raises(ValueError, match='hash mismatch'):
        d22.load_folds(tmp_path)


def fake_grid(folds, repeats=2):
    rows = []
    for rep in range(1, repeats + 1):
        for fold, pack in folds.items():
            for revision in ('before', 'after'):
                for scenario in pack['scenarios']:
                    snapshot = {key: None for key in d21.COMPARE_FIELDS}
                    snapshot['first_status'] = 'fulfilled'
                    snapshot['second_started'] = True
                    if d22.cell(scenario) == ('callback_sync', 'held') and revision == 'before':
                        snapshot['first_status'] = 'pending'
                        snapshot['second_started'] = False
                    row = {'repeat': rep, 'fold': fold, 'revision': revision,
                           'plan_id': scenario['plan_id'], 'snapshot': snapshot,
                           'resources': d21.expected_counts(scenario), 'cleanup': 'finished',
                           'abort_timing': scenario['abort_timing'],
                           'subject_completion': scenario['tasks'][0]['completion']}
                    rows.append(row)
    return rows


def test_factorial_analyzer_counts_cell_not_repetitions(tmp_path, monkeypatch):
    setup_development_folder(tmp_path, monkeypatch)
    folds = d22.make_folds(tmp_path)['folds']
    rows = fake_grid(folds, repeats=2)
    info = d22.analyze_factorial(rows, folds, 2)
    assert info['executions'] == 32
    assert info['changed_paired_executions'] == 2
    assert info['changed_cells'] == ['callback_sync/held']
    assert info['repeat_instability'] == []
    assert info['resource_totals']['fold_a'] == info['resource_totals']['fold_b']
    assert 'not competing' in d22.render_factorial(info).lower() or 'not competing' in d22.render_factorial(info)


def test_reject_missing_duplicate_and_changed_costs(tmp_path, monkeypatch):
    setup_development_folder(tmp_path, monkeypatch)
    folds = d22.make_folds(tmp_path)['folds']
    rows = fake_grid(folds)
    with pytest.raises(ValueError, match='Incomplete'):
        d22.analyze_factorial(rows[:-1], folds, 2)
    with pytest.raises(ValueError, match='Duplicate'):
        d22.analyze_factorial(rows + [copy.deepcopy(rows[0])], folds, 2)
    altered = copy.deepcopy(rows)
    altered[0]['resources']['abort_calls'] += 1
    with pytest.raises(ValueError, match='resource'):
        d22.analyze_factorial(altered, folds, 2)


def test_invalid_repeat_rejected_before_source_loading(tmp_path):
    for value in (0, 6, True, 1.5):
        with pytest.raises(ValueError, match='Repeats'):
            d22.run(tmp_path, repeats=value)


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js unavailable')
def test_full_factorial_pipeline_on_stand_in_not_upstream(tmp_path, monkeypatch):
    setup_development_folder(tmp_path, monkeypatch)
    d22.prepare(tmp_path)
    source = tmp_path / 'fake_queue.mjs'
    source.write_text(FAKE_QUEUE_JS, encoding='utf-8')
    monkeypatch.setattr(d22, 'get_source_bundles', lambda root: {'before': source, 'after': source})
    report = d22.run(tmp_path, repeats=1)
    info = report['analysis']
    assert info['executions'] == 16
    assert info['changed_paired_executions'] == 0
    assert info['changed_cells'] == []
    assert info['repeat_instability'] == []
    assert (tmp_path / d22.FACTORIAL_JSON).is_file()
    assert 'Development-only' in (tmp_path / d22.FACTORIAL_MD).read_text()
