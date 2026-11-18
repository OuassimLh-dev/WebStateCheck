"""Day 24: draft-only independent methodology review handoff.

No model generation, target registration, oracle approval, scoring, or freezing.
Usage:
  python -m webstatecheck.day24_review prepare
  python -m webstatecheck.day24_review audit
  cat results/day24_review_status.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from webstatecheck.day12_holdout import ROOT, assert_day11_lock, canonical_json, sha

TEMPLATES = Path('research/day24_templates')
REVIEW = Path('research/day24_review')
RESULT_MD = Path('results/day24_review_status.md')
RESULT_JSON = Path('results/day24_review_status.json')
FILES = (
    'PUBLIC_METHODS_REVIEW_PACKET.md',
    'ORACLE_REVIEW_FORM.md',
    'SELECTION_AND_EVALUATION_FORM.md',
    'MODEL_ISOLATION_FORM.md',
    'DECISION_RECORD.json',
)
GATES = {
    'independent_target_selection': 'Independently approved selection criteria and new eligible targets',
    'independent_oracle_approval': 'Source-independent target oracles and external review',
    'isolated_generation_approval': 'Isolated model generation and complete cost/provenance plan',
    'v2_preregistration': 'Separately frozen versioned protocol and adjudication rules',
}
# Check the *public methods* packet for development issue/ground-truth leakage.
# This is heuristic; a separate human review remains required.
LEAK_PHRASES = (
    'p-queue', 'final form', 'axios', 'github.com/',
    'before_commit', 'after_commit', 'private_truth',
    'issue #', 'fix commit', 'pull request #',
)


def safe_public_packet(content: str) -> None:
    text = content.casefold()
    hits = [term for term in LEAK_PHRASES if term in text]
    if hits:
        raise ValueError('Public methods packet may leak development case information: ' + ', '.join(hits))
    if 'UNREVIEWED' not in content and 'unreviewed' not in text:
        raise ValueError('Public methods packet must explicitly identify itself as unreviewed')


def prepare(root: Path = ROOT) -> dict[str, Any]:
    lock = assert_day11_lock(root)
    templatedir = root / TEMPLATES
    folder = root / REVIEW
    folder.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    kept: list[str] = []
    for filename in FILES:
        source = templatedir / filename
        if not source.is_file():
            raise FileNotFoundError('Missing Day 24 installation template: ' + str(source))
        target = folder / filename
        if target.exists():
            kept.append(filename)
            continue
        if filename == 'PUBLIC_METHODS_REVIEW_PACKET.md':
            safe_public_packet(source.read_text(encoding='utf-8'))
        # Exclusive mode prevents the tool from overwriting human reviewer edits.
        with target.open('x', encoding='utf-8') as stream:
            stream.write(source.read_text(encoding='utf-8'))
        created.append(filename)
    return {'created': created, 'preserved': kept, 'review_directory': str(folder),
            'day11_lock_sha256': lock, 'approved': False}


def inspect_record(obj: Any) -> dict[str, bool]:
    if not isinstance(obj, dict) or obj.get('record_version') != 'day24-review-draft-v1':
        raise ValueError('Unexpected decision record version')
    if obj.get('review_status') not in {'PENDING_EXTERNAL_REVIEW', 'SUBMITTED_FOR_EXTERNAL_REVIEW'}:
        raise ValueError('Review record cannot declare study approval; independent review and a new freeze are separate')
    statuses: dict[str, bool] = {}
    for gate in GATES:
        entry = obj.get(gate)
        if not isinstance(entry, dict):
            raise ValueError(f'Missing {gate} evidence record')
        reviewer = entry.get('reviewer')
        evidence = entry.get('dated_approval_evidence')
        if reviewer is not None and (not isinstance(reviewer, str) or not reviewer.strip()):
            raise ValueError(f'Invalid {gate} reviewer')
        if evidence is not None and (not isinstance(evidence, str) or not evidence.strip()):
            raise ValueError(f'Invalid {gate} evidence location')
        if (reviewer is None) != (evidence is None):
            raise ValueError(f'{gate} requires both reviewer and dated evidence, or neither')
        statuses[gate] = bool(reviewer and evidence)
    return statuses


def audit(root: Path = ROOT) -> dict[str, Any]:
    lock_hash = assert_day11_lock(root)
    folder = root / REVIEW
    missing = [name for name in FILES if not (folder / name).is_file()]
    if missing:
        raise FileNotFoundError('Review kit is incomplete; run prepare: ' + ', '.join(missing))
    public = (folder / 'PUBLIC_METHODS_REVIEW_PACKET.md').read_text(encoding='utf-8')
    safe_public_packet(public)
    record = json.loads((folder / 'DECISION_RECORD.json').read_text(encoding='utf-8'))
    evidence_claims = inspect_record(record)

    source_day23 = root / 'results/day23_readiness.json'
    if source_day23.is_file():
        old = json.loads(source_day23.read_text(encoding='utf-8'))
        if old.get('classification') != 'RETROSPECTIVE DEVELOPMENT READINESS AUDIT — NOT A HELD-OUT RESULT':
            raise ValueError('Day 23 evidence must retain its development-only classification')
        prior_hash = sha(source_day23)
    else:
        prior_hash = None

    hashes = {name: sha(folder / name) for name in FILES}
    result = {
        'classification': 'DAY24 DRAFT INDEPENDENT REVIEW HANDOFF — NOT APPROVED',
        'day11_lock_sha256': lock_hash,
        'day23_readiness_sha256': prior_hash,
        'review_kit_sha256': hashes,
        'reported_evidence_fields_filled': evidence_claims,
        'outstanding_or_unverified': list(GATES),
        'human_signoffs_independently_verified': False,
        'new_targets_registered_by_day24': False,
        'independent_llm_plans_generated_by_day24': False,
        'v2_protocol_frozen_by_day24': False,
        'heldout_experiments_run_by_day24': 0,
        'approved_to_score_new_targets': False,
    }
    root.joinpath(RESULT_JSON).parent.mkdir(parents=True, exist_ok=True)
    root.joinpath(RESULT_JSON).write_text(canonical_json(result), encoding='utf-8')
    lines = [
        '# Day 24 — Independent methodology review handoff', '',
        '**Status: PENDING EXTERNAL REVIEW. No held-out experiment or v2 approval.**', '',
        f'Day 11 nine-file lock: verified (`{lock_hash}`).',
        f'Day 23 retrospective evidence: {"hash recorded" if prior_hash else "not provided; reviewer should inspect separately"}.', '',
        '## Reviewer approval requirements', '',
    ]
    for key, meaning in GATES.items():
        flag = 'Evidence fields filled, but NOT independently authenticated' if evidence_claims[key] else 'MISSING external evidence'
        lines.append(f'- **{meaning}:** {flag}.')
    lines += [
        '', '## Handoff status', '',
        '- Public methodology packet passed a basic development-case leak-phrase check; this is **not** a full human privacy/leakage review.',
        '- Reviewer documents were created as drafts and can be edited without changing frozen research files.',
        '- An externally reviewed target-specific oracle, approved v2 cohort and a separately hashed protocol are still required.',
        '- No automatic transition from `PENDING` to `APPROVED` is provided.',
        '- The staged development target `t01` remains unsealed.',
        '', '## Next human step', '',
        'Share `research/day24_review/PUBLIC_METHODS_REVIEW_PACKET.md` with an independent supervisor/reviewer and request written feedback. Do not send historical private truth or use this packet as a model test-generation prompt.', '',
    ]
    root.joinpath(RESULT_MD).write_text('\n'.join(lines), encoding='utf-8')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description='Day 24: review kit, not an approval mechanism')
    parser.add_argument('command', choices=['prepare', 'audit'])
    args = parser.parse_args()
    if args.command == 'prepare':
        info = prepare()
        print('Draft reviewer files created:', len(info['created']), 'preserved:', len(info['preserved']))
        print('Review directory:', info['review_directory'])
        print('No independent approval or experimental execution has occurred.')
    else:
        result = audit()
        print('Frozen protocol verified; public methods packet checked.')
        print('Ready to score prospective blinded targets:', result['approved_to_score_new_targets'])
        print('Outstanding independent gates:', len(result['outstanding_or_unverified']))
        print('Saved:', ROOT / RESULT_MD)


if __name__ == '__main__':
    main()
