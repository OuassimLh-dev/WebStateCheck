"""Day 7: isolated upstream Axios CancelToken bug/fix reproduction.

Downloads source files pinned to independently verifiable upstream commits.
Loads unchanged CancelToken.js with a CanceledError constructor stub, then
compares self-unsubscribing listener behavior against a normal-listener control.
Does not execute HTTP requests and does not involve AI or real-world discovery.

Run: python -m webstatecheck.day7_axios --repeats 3
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from webstatecheck.day6_oracles import evaluate_rules

ROOT = Path(__file__).resolve().parent.parent
CASE = ROOT / 'realworld' / 'axios_case'
SOURCE_DIR = CASE / 'upstream_sources'
RESULT_DIR = ROOT / 'results'
RULES = ROOT / 'research' / 'oracles' / 'day7_axios_rules.json'
REVISIONS = {
    'before': '27280ec260bb353b57807ebcf8aa30b772663405',
    'after': 'de48c5d626e056d5e6056099c881b878103fc20e',
}
SCENARIOS = ('unsubscribe_during_notification', 'stable_listeners')
REPOSITORY = 'https://github.com/axios/axios'


def source_url(commit: str) -> str:
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('Expected full 40-character upstream commit hash')
    return f'https://raw.githubusercontent.com/axios/axios/{commit}/lib/cancel/CancelToken.js'


def ensure_upstream_source(label: str, commit: str) -> dict:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    target = SOURCE_DIR / f'{label}_CancelToken.js'
    if not target.is_file():
        url = source_url(commit)
        print(f'+ Download upstream {label} CancelToken.js at {commit}', flush=True)
        request = Request(url, headers={'User-Agent':'WebStateCheck-reproduction/1.0'})
        with urlopen(request, timeout=40) as response:
            content = response.read()
        if not content.startswith(b"'use strict';") or b'function CancelToken(executor)' not in content:
            raise RuntimeError(f'Unexpected upstream file contents for {url}')
        # Atomic write to protect against interrupted downloads.
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(content)
        temporary.replace(target)
    content = target.read_bytes()
    if b'function CancelToken(executor)' not in content or b'module.exports = CancelToken' not in content:
        raise RuntimeError(f'Invalid cached source file {target}; remove and redownload it')
    return {'path':str(target), 'url':source_url(commit), 'sha256':hashlib.sha256(content).hexdigest(), 'bytes':len(content)}


def axios_facts(probe: dict) -> dict:
    # Deliberately excludes label, commit, and expected before/after behavior.
    return {
        'cancellation_requested': probe.get('cancellation_requested'),
        'all_listeners_notified': probe.get('all_listeners_notified'),
        'unexpected_exception': probe.get('unexpected_exception'),
    }


def assess_probe(probe: dict, rules: list[dict]) -> dict:
    return evaluate_rules('axios', axios_facts(probe), rules)


def invoke_probe(source: Path, label: str, commit: str, scenario: str) -> dict:
    command = ['node', str(CASE / 'probe.cjs'), str(source), label, commit, scenario]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    try:
        obj = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Probe produced invalid JSON: {completed.stdout!r}; stderr={completed.stderr!r}') from exc
    if obj.get('upstream_commit') != commit or obj.get('scenario') != scenario or obj.get('label') != label:
        raise RuntimeError('Probe metadata mismatch')
    return obj


def run(repeats: int = 3, output: Path = RESULT_DIR) -> dict:
    if repeats < 1 or repeats > 100:
        raise ValueError('Choose a repeat count between 1 and 100')
    if shutil.which('node') is None:
        raise RuntimeError('Node.js not found; install Node.js first')
    config = json.loads(RULES.read_text(encoding='utf-8'))
    rules = config['rules']
    if not rules or any(r.get('source') != 'axios' for r in rules):
        raise RuntimeError('Day 7 rule configuration is malformed')
    sources = {name:ensure_upstream_source(name, sha) for name,sha in REVISIONS.items()}
    observations = []
    for repetition in range(1, repeats+1):
        for scenario in SCENARIOS:
            for label, commit in REVISIONS.items():
                raw = invoke_probe(Path(sources[label]['path']), label, commit, scenario)
                assessment = assess_probe(raw, rules)
                record = {**raw, 'repetition': repetition,
                          'verdict':assessment['verdict'], 'rule_results':assessment['rules']}
                observations.append(record)
                print(f'[{label}] repeat={repetition} {scenario}: called={raw["notified_listener_ids"]}, '
                      f'unhandled={len(raw["unhandled_rejections"])}, verdict={assessment["verdict"]}',flush=True)
    counts = {label:dict(Counter(r['verdict'] for r in observations if r['label']==label)) for label in REVISIONS}
    expected = all(
        r['verdict'] == ('violation' if r['label']=='before' else 'clear')
        for r in observations if r['scenario']=='unsubscribe_during_notification'
    ) and all(r['verdict']=='clear' for r in observations if r['scenario']=='stable_listeners')
    data = {
        'study':'Day 7: second upstream bug/fix case (isolated Axios CancelToken)',
        'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'source':'Axios issue #4260 / PR #4261', 'source_url':REPOSITORY,
        'scope':'Unmodified upstream CancelToken.js; CanceledError dependency stubbed; no HTTP request or browser',
        'revisions':REVISIONS, 'sources':sources, 'repetitions':repeats,
        'counts':counts, 'expected_before_after_pattern_observed':expected,
        'observations':observations,
    }
    output.mkdir(parents=True,exist_ok=True)
    (output/'day7_axios_observations.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    lines = [
        '# Day 7 — Independent upstream Axios cancellation case', '',
        '**Upstream evidence:** Axios issue [#4260](https://github.com/axios/axios/issues/4260), fix PR [#4261](https://github.com/axios/axios/pull/4261).',
        '**Scope:** Actual pinned `CancelToken.js` module, loaded without changing source. An isolated `CanceledError` class replaces the original dependency. No HTTP requests or browser were involved.',
        '**Method:** Self-unsubscribing event listeners (targeted case) and stable listeners (negative control), with a hand-authored invariant independent of the source revision label.', '',
        '| Revision | Commit | Scenario | Trials | Violations | Clear | Inconclusive |',
        '|---|---|---|---:|---:|---:|---:|',
    ]
    for label, sha in REVISIONS.items():
        for scenario in SCENARIOS:
            rows=[r for r in observations if r['label']==label and r['scenario']==scenario]
            by=Counter(r['verdict'] for r in rows)
            lines.append(f'| {label} | `{sha[:9]}` | {scenario} | {len(rows)} | {by["violation"]} | {by["clear"]} | {by["inconclusive"]} |')
    lines += ['',f'**Expected before/after pattern reproduced in this isolated probe:** `{expected}`.', '',
              '### Provenance', '']
    for label,info in sources.items():
        lines.append(f'- `{label}`: [{REVISIONS[label]}]({REPOSITORY}/commit/{REVISIONS[label]}), source SHA-256 `{info["sha256"]}`')
    lines += ['', '### Limitations', '',
              '- This is a known-bug regression reproduction, **not autonomous defect discovery**.',
              '- The original `CanceledError` dependency is stubbed, and no Axios HTTP adapter is exercised.',
              '- The invariant and scenario are tailored to the documented cancellation issue.',
              '- Repeated runs of one module do not establish general detection performance.',
              '- AI is not part of this experiment.',
              '', 'Next: integrate multiple independent bug/fix cases under comparable oracles and examine whether tests can be generated without reading the historical issue first.', '']
    (output/'day7_axios_summary.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Saved:',output/'day7_axios_observations.json')
    print('Saved:',output/'day7_axios_summary.md')
    if not expected:
        print('ATTENTION: Targeted reproduction did not match the historical expected pattern. Investigate data; do not alter it.')
    return data


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--output',type=Path,default=RESULT_DIR)
    args=parser.parse_args()
    try:
        run(args.repeats,args.output)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'Day 7 reproduction failed; no valid result claimed: {exc}',file=sys.stderr)
        raise SystemExit(1) from exc

if __name__=='__main__':
    main()
