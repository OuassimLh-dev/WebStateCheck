"""Day 5: test actual final-form source at two pinned upstream Git commits.

Before first run requires GitHub and npm access. No measured outcomes are hardcoded.
Run from project root: python -m webstatecheck.day5_realworld
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASE = ROOT / 'realworld' / 'finalform_case'
REPO = CASE / 'upstream'
VERSIONS = CASE / 'versions'
BUILD = CASE / 'build'
OUT = ROOT / 'results'
REVISIONS = {'before': 'ec4de30', 'after': 'b56bf28'}
REPOSITORY = 'https://github.com/final-form/final-form.git'


def invoke(command, cwd=None, capture=False):
    print('+', ' '.join(map(str, command)), flush=True)
    result = subprocess.run(
        list(map(str, command)), cwd=cwd, text=True,
        check=True, capture_output=capture,
    )
    return result.stdout.strip() if capture else None


def verify_tools():
    for cmd in ('git', 'node', 'npm'):
        if shutil.which(cmd) is None:
            raise RuntimeError(f'{cmd} is required. Install Git and Node.js/npm first.')


def prepare():
    CASE.mkdir(parents=True, exist_ok=True)
    VERSIONS.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    verify_tools()
    if not REPO.exists():
        invoke(['git', 'clone', '--filter=blob:none', REPOSITORY, REPO])
    for name, rev in REVISIONS.items():
        sha = invoke(['git', '-C', REPO, 'rev-parse', '--verify', f'{rev}^{{commit}}'], capture=True)
        target = VERSIONS / name
        if not target.exists():
            invoke(['git', '-C', REPO, 'worktree', 'add', '--detach', target, sha])
        actual = invoke(['git', '-C', target, 'rev-parse', 'HEAD'], capture=True)
        if actual != sha:
            raise RuntimeError(f'Existing worktree {target} points to {actual}, expected {sha}. Please inspect it; not overwriting.')
    if not (CASE / 'node_modules' / '.bin' / 'esbuild').exists():
        invoke(['npm', 'install', '--no-audit', '--no-fund'], cwd=CASE)
    binary = CASE / 'node_modules' / '.bin' / 'esbuild'
    for name in REVISIONS:
        entry = VERSIONS / name / 'src' / 'index.ts'
        if not entry.exists():
            raise RuntimeError(f'Upstream source missing: {entry}')
        invoke([binary, entry, '--bundle', '--platform=node', '--format=cjs',
                '--target=node18', f'--outfile={BUILD / (name + ".cjs")}'])
    print('Prepared pinned upstream bundles:', BUILD)


def collect():
    OUT.mkdir(exist_ok=True)
    observations = []
    for name, rev in REVISIONS.items():
        sha = invoke(['git', '-C', VERSIONS / name, 'rev-parse', 'HEAD'], capture=True)
        artifact = BUILD / (name + '.cjs')
        cmd = ['node', CASE / 'probe.cjs', artifact, name, sha]
        raw = invoke(cmd, cwd=CASE, capture=True)
        result = json.loads(raw)
        observations.append(result)
        print(f'[{name}] old validation resolved => validating={result["after_older_resolved"]["validating"]}, violation={result["violation"]}')
    metadata = {
        'study': 'Day 5 external real-world reproduction',
        'evidence_scope': 'Single externally documented library bug, pinned before/after commits. Probe crafted for known upstream issue; not autonomous discovery.',
        'observations': observations,
    }
    (OUT / 'day5_realworld.json').write_text(json.dumps(metadata, indent=2) + '\n')
    before, after = observations
    observed_expected = before['violation'] is True and after['violation'] is False
    lines = [
        '# Day 5 — Upstream bug/fix reproduction', '',
        '**External source:** final-form/final-form issue #509, fixed by PR #513.',
        '**Important:** This is a targeted regression reproducer for a known real-world issue, not proof of general bug-detection accuracy.', '',
        '| Revision | Commit | `validating` after old request finishes (new still pending) | Violation |',
        '|---|---|---|---|',
    ]
    for r in observations:
        lines.append(f'| {r["label"]} | `{r["upstream_commit"]}` | `{r["after_older_resolved"]["validating"]}` | `{r["violation"]}` |')
    lines += ['', f'**Expected bug/fix behavior reproduced:** {observed_expected}', '',
              'The code is the actual upstream TypeScript bundled with esbuild; only the scenario driver is ours.',
              'A missing difference, unexpected exception, or installation error needs investigation; do not edit observations to match expectations.', '',
              'Next: adapt the oracle into a general configurable asynchronous-state monitor, add several unrelated upstream bug/fix pairs, and eventually compare AI-assisted candidate generation.', '']
    report = OUT / 'day5_realworld_summary.md'
    report.write_text('\n'.join(lines))
    print('Saved:', OUT / 'day5_realworld.json')
    print('Saved:', report)
    if not observed_expected:
        print('NOTE: Unexpected behavior across the pinned versions. Investigate before drawing conclusions.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-prepare', action='store_true', help='Use existing cloned/bundled upstream revisions')
    args = parser.parse_args()
    try:
        if not args.skip_prepare:
            prepare()
        collect()
    except (subprocess.CalledProcessError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f'Day 5 failed before producing valid results: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
