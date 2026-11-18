import hashlib
import json
from pathlib import Path
import pytest

from webstatecheck.day11_audit import FROZEN
from webstatecheck.day12_holdout import canonical_json, valid_public, valid_private, paths, verify
from webstatecheck.day13_target import (
    PUBLIC, PRIVATE, BEFORE, AFTER, prepare, seal_reviewed, TARGET, verify_source
)


def fake_root(root: Path) -> Path:
    hashes = {}
    for rel in FROZEN:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('frozen-' + rel, encoding='utf-8')
        hashes[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    (root / 'research/day11_future_protocol_lock.json').write_text(canonical_json({'file_sha256': hashes}))
    return root


def test_registration_is_structurally_valid():
    valid_public(PUBLIC, TARGET)
    valid_private(PRIVATE, TARGET)
    assert len(BEFORE) == len(AFTER) == 40


def test_prepare_stages_separate_records_without_sealing(tmp_path):
    root = fake_root(tmp_path)
    a, b = prepare(root)
    assert a.exists() and b.exists()
    assert 'issue_url' not in a.read_text()
    assert 'before_commit' not in a.read_text()
    assert 'github.com' not in a.read_text()
    assert 'issue_url' in b.read_text()
    assert not paths(root, TARGET)[1].exists()
    with pytest.raises(FileExistsError):
        prepare(root)


def test_no_seal_without_review(tmp_path):
    root = fake_root(tmp_path)
    prepare(root)
    with pytest.raises(ValueError, match='public-reviewed'):
        seal_reviewed(root)


def test_no_seal_without_source_verification(tmp_path):
    root = fake_root(tmp_path)
    prepare(root)
    with pytest.raises(FileNotFoundError):
        seal_reviewed(root, public_reviewed=True)


def test_seal_rejects_drift(tmp_path):
    root = fake_root(tmp_path)
    a, b = prepare(root)
    result = root / 'results/day13_source_verification.json'
    result.parent.mkdir(parents=True)
    result.write_text(canonical_json({'public_spec_sha256': hashlib.sha256(a.read_bytes()).hexdigest(),
                                      'private_truth_sha256': hashlib.sha256(b.read_bytes()).hexdigest(),
                                      'before_commit': BEFORE, 'after_commit': AFTER}))
    data = json.loads(a.read_text())
    data['reset_strategy'] += ' changed'
    a.write_text(canonical_json(data))
    with pytest.raises(ValueError, match='changed'):
        seal_reviewed(root, public_reviewed=True)


def test_seal_after_review_and_verified_record(tmp_path):
    root = fake_root(tmp_path)
    a, b = prepare(root)
    result = root / 'results/day13_source_verification.json'
    result.parent.mkdir(parents=True)
    result.write_text(canonical_json({'public_spec_sha256': hashlib.sha256(a.read_bytes()).hexdigest(),
                                      'private_truth_sha256': hashlib.sha256(b.read_bytes()).hexdigest(),
                                      'before_commit': BEFORE, 'after_commit': AFTER}))
    seal_reviewed(root, public_reviewed=True)
    assert verify(root, TARGET)['target_id'] == TARGET
    packet = (root / 'research/holdout_sealed/t01/generator_packet.json').read_text()
    assert 'github.com' not in packet and 'issue_url' not in packet


def test_verify_source_requires_staging(tmp_path):
    root = fake_root(tmp_path)
    with pytest.raises(FileNotFoundError):
        verify_source(root)
