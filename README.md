# WebStateCheck

**Timing-aware test programs for asynchronous JavaScript**  
*Independent software testing research prototype • November 2026*

WebStateCheck explores how test-program structure, cancellation scheduling, and observable state invariants affect the detection of asynchronous JavaScript defects. The repository contains a controlled browser fixture, a declarative correctness checker, reproducible testing tools, development experiment protocols, and tests for the research infrastructure.

## What was investigated

- A local buggy/fixed browser fixture illustrating stale search responses and error-state handling.
- Targeted reproductions of **documented historical defects** in the open-source **Final Form**, **Axios**, and **p-queue** projects using pinned versions (upstream code is not redistributed here).
- A `p-queue` coverage-gap study: a restricted external-action grammar showed no revision differences in 616 development executions, while callback-synchronous cancellation exposed a documented before/after difference in subsequent targeted experiments.
- Timing-aware test-program descriptions, cancellation/resource accounting, and tests of random versus deterministic heuristic plan feasibility.
- A small, **context-contaminated synthetic LLM pilot** retained as exploratory evidence only. It does not establish LLM superiority.

**Research status:** prototype and unpublished technical manuscript. The project has **not** demonstrated superiority over other testing methods on independently selected held-out targets; it is **not** a peer-reviewed publication.

## Getting started

Requirements: Python 3.10+; Node.js for JavaScript test harnesses; Chromium for Playwright browser experiments.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pytest -q
```

The included Python suite primarily exercises test logic and infrastructure, including isolated JavaScript harness checks. Tests passing **do not** mean all source-pinned historical reproductions ran in this fresh checkout. Those experiments additionally require the corresponding pinned upstream source trees/bundles.

To try the controlled browser fixture locally:

```bash
python -m webstatecheck.experiment --repeats 3
```

To validate the included data-driven timing plans without historical source bundles:

```bash
python -m webstatecheck.day19_timing validate
```

The Day 20 resource-budget tools and later experiment audits require saved development manifests that are intentionally excluded from this public source copy. Run those commands in the original research workspace if you have the corresponding records; do not regenerate or invent provenance to make an audit pass.

For the local application, run `python -m webstatecheck.server` and open `http://127.0.0.1:8765/?mode=buggy` or `?mode=fixed`.

## Repository layout

| Path | Purpose |
|---|---|
| `webstatecheck/` | Python experiment orchestration, validation, oracles, and audits |
| `realworld/` | JavaScript probes and integration harnesses (no checked-in upstream dependencies) |
| `fixtures/` | Synthetic local browser application |
| `research/` | Selected public development protocols, safe example plans, and oracle rules |
| `tests/` | Regression/unit tests for the research infrastructure |

## Evidence and limitations

Observations on the seeded browser fixture are not measurements of performance on arbitrary web apps. Pinned historical bug reproductions are **known-bug regression tests**, not the discovery of novel defects. A repeated failing execution is not an independent defect. Timing/profile combinations were chosen after the `p-queue` historical issue was known. Earlier research design files are preserved for provenance and may describe proposals rather than approved prospective studies.

The protocol for a blinded multi-target comparison, independent behavioral oracle adjudication, and isolated model-test generation has **not** been fully validated or executed. No claim of AI effectiveness or generalization follows from the current evidence.

## Manuscript and attribution

*WebStateCheck: Timing-Aware Test Programs for Asynchronous JavaScript* (Ouassim Lahraoui, 2026), **unpublished independent technical manuscript**. The manuscript is supplied separately from this source distribution.

Public upstream software is credited to its original maintainers. This repository includes original research harnesses, not copied upstream application source trees.

## Technical report

[WebStateCheck: Timing-Aware Test Programs for Asynchronous JavaScript (PDF)](docs/WebStateCheck_Technical_Report_Updated_2026.pdf) — independent unpublished technical report, version 1.1 (19 November 2026), not peer reviewed. For limitations and artifact coverage, see [Public artifact scope](docs/RESEARCH_ARTIFACT_SCOPE.md).
