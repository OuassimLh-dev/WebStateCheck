"""Day 23 only validates saved synthetic evidence in tests; no real-source claim."""
import copy
import json
from pathlib import Path

import pytest

from webstatecheck import day23_readiness as d23
from webstatecheck import day22_pairing as d22
from webstatecheck import day21_adapter as d21
from webstatecheck.day20_budget import make_pack
from webstatecheck.day12_holdout import canonical_json, sha


def dataset(tmp_path: Path, monkeypatch, repeats=2):
    source = make_pack('random', 20261118)
    folds = {}
    for fold in ('fold_a', 'fold_b'):
        pack = copy.deepcopy(source)
        for i, scenario in enumerate(pack['scenarios'], 1):
            scenario['plan_id'] = f'{fold}-{i}'
            if fold == 'fold_b':
                current = scenario['tasks'][0]['completion']
                scenario['tasks'][0]['completion'] = 'held' if current == 'immediate' else 'immediate'
        folds[fold] = pack
    manifest = {'plan_sha256': {'fold_a': 'abcdef', 'fold_b': 'fedcba'}}
    runner = tmp_path / d21.RUNNER
    runner.parent.mkdir(parents=True)
    runner.write_text('test runner source content', encoding='utf-8')
    monkeypatch.setattr(d23.d22, 'load_folds', lambda root: (folds, manifest))
    monkeypatch.setattr(d23, 'assert_day11_lock', lambda root: 'test-lock')
    records = []
    for rep in range(1, repeats + 1):
        for fold, pack in folds.items():
            for revision in ('before', 'after'):
                for s in pack['scenarios']:
                    snapshot = {key: None for key in d21.COMPARE_FIELDS}
                    snapshot['first_status'] = 'fulfilled'
                    snapshot['second_started'] = True
                    if d22.cell(s) == ('callback_sync', 'held') and revision == 'before':
                        snapshot['first_status'] = 'pending'
                        snapshot['second_started'] = False
                    records.append({'repeat': rep, 'fold': fold, 'revision': revision,
                                    'plan_id': s['plan_id'], 'snapshot': snapshot,
                                    'resources': d21.expected_counts(s), 'cleanup': 'finished',
                                    'abort_timing': s['abort_timing'],
                                    'subject_completion': s['tasks'][0]['completion']})
    info = d22.analyze_factorial(records, folds, repeats)
    report = {'classification': 'DAY22 DEVELOPMENT FACTORIAL, NOT HOLDOUT',
              'plan_sha256': copy.deepcopy(manifest['plan_sha256']), 'runner_sha256': sha(runner),
              'repeats': repeats, 'records': records, 'analysis': info,
              'heldout': False, 'llm_generated': False}
    output = tmp_path / d22.FACTORIAL_JSON
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report), encoding='utf-8')
    return report, output


def replace(output: Path, report: dict):
    output.write_text(canonical_json(report), encoding='utf-8')


def test_replay_counts_distinct_cells_not_repeated_triggers(tmp_path, monkeypatch):
    dataset(tmp_path, monkeypatch)
    info = d23.inspect(tmp_path)
    assert info['executions'] == 32
    assert info['timing_profile_cells'] == 8
    assert info['changed_execution_pairs'] == 2
    assert info['changed_distinct_cells'] == 1
    assert info['changed_cell_names'] == ['callback_sync/held']
    assert info['repeat_instability'] == 0
    assert info['balanced_execution_costs'] is True


def test_audit_outputs_provenance_but_not_approval(tmp_path, monkeypatch):
    _, source = dataset(tmp_path, monkeypatch)
    original = source.read_bytes()
    info = d23.audit(tmp_path)
    assert info['ready_for_blinded_study'] is False
    assert all(g['status'] == 'NOT_VERIFIED' for g in info['prospective_gates'].values())
    assert (tmp_path / d23.SUMMARY).is_file()
    assert (tmp_path / d23.JSON_OUTPUT).is_file()
    assert source.read_bytes() == original
    assert 'NOT READY' in (tmp_path / d23.SUMMARY).read_text()
    assert not (tmp_path / 'research/holdout_sealed/t01').exists()


def test_reject_tampered_plan_hash(tmp_path, monkeypatch):
    report, output = dataset(tmp_path, monkeypatch)
    report['plan_sha256']['fold_a'] = 'wrong'
    replace(output, report)
    with pytest.raises(ValueError, match='plan SHA'):
        d23.inspect(tmp_path)


def test_reject_tampered_runner_hash(tmp_path, monkeypatch):
    _, output = dataset(tmp_path, monkeypatch)
    (tmp_path / d21.RUNNER).write_text('runner changed', encoding='utf-8')
    with pytest.raises(ValueError, match='runner hash'):
        d23.inspect(tmp_path)


def test_reject_falsely_labeled_heldout_or_ai(tmp_path, monkeypatch):
    report, output = dataset(tmp_path, monkeypatch)
    for field in ('heldout', 'llm_generated'):
        tampered = copy.deepcopy(report)
        tampered[field] = True
        replace(output, tampered)
        with pytest.raises(ValueError, match='classification'):
            d23.inspect(tmp_path)


def test_reject_modified_saved_analysis(tmp_path, monkeypatch):
    report, output = dataset(tmp_path, monkeypatch)
    report['analysis']['changed_paired_executions'] = 0
    replace(output, report)
    with pytest.raises(ValueError, match='reproducible'):
        d23.inspect(tmp_path)


def test_reject_missing_row(tmp_path, monkeypatch):
    report, output = dataset(tmp_path, monkeypatch)
    report['records'].pop()
    replace(output, report)
    with pytest.raises(ValueError, match='Incomplete'):
        d23.inspect(tmp_path)


def test_reject_modified_executed_resource(tmp_path, monkeypatch):
    report, output = dataset(tmp_path, monkeypatch)
    report['records'][0]['resources']['submissions'] = 19
    replace(output, report)
    with pytest.raises(ValueError, match='resource'):
        d23.inspect(tmp_path)


def test_reject_duplicate_execution(tmp_path, monkeypatch):
    report, output = dataset(tmp_path, monkeypatch)
    report['records'].append(copy.deepcopy(report['records'][0]))
    replace(output, report)
    with pytest.raises(ValueError, match='Duplicate'):
        d23.inspect(tmp_path)


def test_missing_saved_evidence_reports_real_blocker(tmp_path, monkeypatch):
    _, output = dataset(tmp_path, monkeypatch)
    output.unlink()
    with pytest.raises(FileNotFoundError, match='missing'):
        d23.inspect(tmp_path)


def test_prospectively_unapproved_even_with_no_differences(tmp_path, monkeypatch):
    report, output = dataset(tmp_path, monkeypatch)
    for row in report['records']:
        row['snapshot']['first_status'] = 'fulfilled'
        row['snapshot']['second_started'] = True
    folds, _ = d22.load_folds(tmp_path)
    report['analysis'] = d22.analyze_factorial(report['records'], folds, 2)
    replace(output, report)
    info = d23.inspect(tmp_path)
    assert info['changed_distinct_cells'] == 0
    assert info['ready_for_blinded_study'] is False
