"""Day 20 tests only verify structural and semantic-budget accounting.

No unit test implies application correctness or a blinded LLM result.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from webstatecheck import day20_budget as d20


def candidate(method='random', seed=20261118):
    return d20.make_pack(method, seed)


def test_generated_vectors_equal():
    random = d20.validate_pack(candidate('random'))
    heuristic = d20.validate_pack(candidate('heuristic'))
    assert random == heuristic
    assert random['scenarios'] == 4
    assert random['submissions'] == 8
    assert random['abort_calls'] == 3
    assert random['callback_abort_calls'] == 2
    assert random['external_abort_calls'] == 1
    assert random['microtask_schedules'] == 1
    assert random['passive_snapshots'] == 4
    assert random['total_observe_window_ms'] == 200


def test_random_repeatable():
    assert candidate('random', 100) == candidate('random', 100)
    assert candidate('random', 101) != candidate('random', 100)


def test_heuristic_repeatable():
    assert candidate('heuristic', 100) == candidate('heuristic', 101)


@pytest.mark.parametrize('bad', [-1, 2**32, 3.14, True, None])
def test_invalid_seed_rejected(bad):
    with pytest.raises(ValueError):
        d20.make_pack('random', bad)


def test_unknown_generator_rejected():
    with pytest.raises(ValueError):
        d20.make_pack('llm', 20261118)


def test_expected_method_restriction():
    with pytest.raises(ValueError, match='mismatched'):
        d20.validate_pack(candidate('random'), expected_method='heuristic')


@pytest.mark.parametrize('mutator', [
    lambda p: p.update({'schema_version': 'wrong'}),
    lambda p: p.update({'domain': 'web_app'}),
    lambda p: p.update({'private_issue': 'secret'}),
    lambda p: p.update({'scenarios': []}),
    lambda p: p['scenarios'][0].update({'plan_id': p['scenarios'][1]['plan_id']}),
    lambda p: p['scenarios'][0].update({'revision': 'before'}),
    lambda p: p['scenarios'][0].update({'abort_timing': 'not_supported'}),
    lambda p: p['scenarios'][0]['tasks'].pop(),
    lambda p: p['scenarios'][0]['tasks'][0].update({'abort_signal': False}),
    lambda p: p['scenarios'][0]['tasks'][1].update({'completion': 'held'}),
    lambda p: p['scenarios'][0].update({'tasks': ['quick', 'quick']}),
    lambda p: p['observation'].update({'observe_ms': 51}),
    lambda p: p['observation'].update({'timeout_ms': True}),
    lambda p: p['observation'].update({'snapshot_policy': 'post_cleanup'}),
])
def test_invalid_plan_is_rejected(mutator):
    pack = copy.deepcopy(candidate())
    mutator(pack)
    with pytest.raises((ValueError, TypeError)):
        d20.validate_pack(pack)


def test_missing_timing_stratum_rejected():
    pack = candidate()
    pack['scenarios'][0]['abort_timing'] = pack['scenarios'][1]['abort_timing']
    with pytest.raises(ValueError, match='timing stratum'):
        d20.validate_pack(pack)


def test_profile_margins_rejected():
    pack = candidate()
    for scenario in pack['scenarios']:
        scenario['tasks'][0]['completion'] = 'held'
    with pytest.raises(ValueError, match='Exactly two'):
        d20.validate_pack(pack)


def test_validation_does_not_mutate_input():
    pack = candidate()
    saved = copy.deepcopy(pack)
    d20.validate_pack(pack)
    assert pack == saved


def _root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(d20, 'assert_day11_lock', lambda root: 'test-lock-sha')
    proto = tmp_path / d20.PROTOCOL
    proto.parent.mkdir(parents=True, exist_ok=True)
    proto.write_text('Test-only: versioned protocol proposal.\n', encoding='utf-8')
    return tmp_path


def test_prepare_then_audit(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    prepared = d20.prepare(root, seed=20261118)
    assert set(prepared) == {'random', 'heuristic'}
    report = d20.audit(root)
    assert report['semantic_budget_vectors_equal'] is True
    assert report['actual_execution'] is False
    assert report['llm_generated'] is False
    assert report['known_issue_contamination'] is True
    md = (root / 'results/day20_budget_audit.md').read_text(encoding='utf-8')
    assert 'not an actual benchmark' in json.dumps(report)
    assert 'No application execution' in md
    assert 'Heuristic construction used known development context' in md


def test_prepare_idempotent_and_no_overwrite(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    original = d20.prepare(root, seed=1)
    assert original == d20.prepare(root, seed=1)
    paths = [root / d20.CANDIDATES / f'{method}.json' for method in d20.METHODS]
    before = [f.read_bytes() for f in paths]
    with pytest.raises(FileExistsError):
        d20.prepare(root, seed=2)
    assert [f.read_bytes() for f in paths] == before


def test_no_llm_candidate_file_generated(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d20.prepare(root)
    assert not (root / d20.CANDIDATES / 'llm.json').exists()


def test_corrupted_budget_pack_refused(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    d20.prepare(root)
    file = root / d20.CANDIDATES / 'heuristic.json'
    pack = json.loads(file.read_text(encoding='utf-8'))
    pack['scenarios'][0]['abort_timing'] = 'none'
    file.write_text(d20.canonical_json(pack), encoding='utf-8')
    with pytest.raises(ValueError):
        d20.audit(root)


def test_audit_requires_both_generated_packs(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError):
        d20.audit(root)


def test_existing_conflict_refused_before_writing_other_pack(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    folder = root / d20.CANDIDATES
    folder.mkdir(parents=True)
    (folder / 'random.json').write_text('DO NOT OVERWRITE', encoding='utf-8')
    with pytest.raises(FileExistsError):
        d20.prepare(root)
    assert (folder / 'random.json').read_text(encoding='utf-8') == 'DO NOT OVERWRITE'
    assert not (folder / 'heuristic.json').exists()
