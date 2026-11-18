"""Development review kit tests. No independent human sign-off is simulated as real."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from webstatecheck import day24_review as d


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch):
    # Use the installed package templates, while keeping generated files in tmp.
    templates = Path(__file__).resolve().parents[1] / d.TEMPLATES
    dest = tmp_path / d.TEMPLATES
    dest.mkdir(parents=True)
    for name in d.FILES:
        shutil.copyfile(templates / name, dest / name)
    monkeypatch.setattr(d, 'assert_day11_lock', lambda root: '0' * 64)
    return tmp_path


def test_prepare_preserves_user_review_edits(sandbox):
    first = d.prepare(sandbox)
    assert len(first['created']) == 5
    p = sandbox / d.REVIEW / 'ORACLE_REVIEW_FORM.md'
    p.write_text('External reviewer notes to preserve', encoding='utf-8')
    second = d.prepare(sandbox)
    assert not second['created']
    assert len(second['preserved']) == 5
    assert p.read_text(encoding='utf-8') == 'External reviewer notes to preserve'


def test_audit_explicitly_refuses_to_claim_approval(sandbox):
    d.prepare(sandbox)
    result = d.audit(sandbox)
    assert result['approved_to_score_new_targets'] is False
    assert result['heldout_experiments_run_by_day24'] == 0
    assert len(result['outstanding_or_unverified']) == 4
    assert not any(result['reported_evidence_fields_filled'].values())
    report = (sandbox / d.RESULT_MD).read_text(encoding='utf-8')
    assert 'PENDING EXTERNAL REVIEW' in report
    assert 'unsealed' in report


def test_missing_files_cannot_pass(sandbox):
    d.prepare(sandbox)
    (sandbox / d.REVIEW / 'ORACLE_REVIEW_FORM.md').unlink()
    with pytest.raises(FileNotFoundError):
        d.audit(sandbox)


@pytest.mark.parametrize('phrase', ['p-queue', 'axios', 'Final Form', 'github.com/', 'before_commit'])
def test_leak_check_rejects_case_identifiers(phrase):
    with pytest.raises(ValueError):
        d.safe_public_packet('UNREVIEWED\n' + phrase)


def test_public_packet_requires_unreviewed_label():
    with pytest.raises(ValueError):
        d.safe_public_packet('Method plan with no review status')


def test_approval_is_not_machine_authorized_even_with_fields(sandbox):
    d.prepare(sandbox)
    p = sandbox / d.REVIEW / 'DECISION_RECORD.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    for key in d.GATES:
        data[key]['reviewer'] = 'person recorded by user'
        data[key]['dated_approval_evidence'] = 'evidence/record.pdf'
    p.write_text(json.dumps(data), encoding='utf-8')
    result = d.audit(sandbox)
    assert all(result['reported_evidence_fields_filled'].values())
    assert not result['human_signoffs_independently_verified']
    assert not result['approved_to_score_new_targets']


def test_partial_claim_is_rejected(sandbox):
    d.prepare(sandbox)
    p = sandbox / d.REVIEW / 'DECISION_RECORD.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    data['independent_oracle_approval']['reviewer'] = 'no supporting evidence'
    p.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='both reviewer and dated evidence'):
        d.audit(sandbox)


def test_unexpected_status_cannot_claim_approval(sandbox):
    d.prepare(sandbox)
    p = sandbox / d.REVIEW / 'DECISION_RECORD.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    data['review_status'] = 'APPROVED'
    p.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='cannot declare study approval'):
        d.audit(sandbox)


def test_day23_provenance_must_remain_development(sandbox):
    d.prepare(sandbox)
    dpath = sandbox / 'results/day23_readiness.json'
    dpath.parent.mkdir()
    dpath.write_text(json.dumps({'classification': 'REAL HELDOUT'}), encoding='utf-8')
    with pytest.raises(ValueError, match='development-only'):
        d.audit(sandbox)


def test_original_template_is_safe():
    path = Path(__file__).resolve().parents[1] / d.TEMPLATES / 'PUBLIC_METHODS_REVIEW_PACKET.md'
    d.safe_public_packet(path.read_text(encoding='utf-8'))
