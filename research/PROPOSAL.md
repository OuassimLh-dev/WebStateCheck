# WebStateCheck — Initial Research Proposal

**Date:** 2026-11-16  
**Status:** Proposal + seed-fixture baseline; novelty, accuracy, and publication suitability **not established**.

## 1. Motivation

Modern JavaScript interfaces use asynchronous requests and callbacks. Race-like UI state bugs may occur when responses arrive out of order, and loading states may remain unresolved when an error is not handled correctly. These bugs can be intermittent and difficult to reproduce with ordinary happy-path testing.

We propose combining **AI-generated candidate interaction sequences** with **deterministic, browser-executed state checks** and potentially lightweight code analysis. The AI would *suggest* where to test; the browser test would *verify* observable failures. This is a hypothesis to evaluate, not an already validated method.

## 2. Scope and research questions

- **RQ1 (Feasibility):** Can deterministic browser checks reliably distinguish known faulty and repaired implementations for selected asynchronous UI bugs?
- **RQ2 (Detection):** Does AI-assisted scenario generation improve detection recall at a fixed execution budget versus unguided/heuristic browser test generation?
- **RQ3 (Cost):** How do detection yield, false positives, runtime, and LLM token cost vary across approaches?
- **RQ4 (Generalization):** Does any observed improvement transfer from seeded fixtures to independently collected real-world bug-fix pairs?

## 3. Operational definitions and oracles

**Bug family A — stale-response overwrite.** When the user changes their search query from old to new, the final displayed result after both requests complete must correspond to the latest query, not the earliest response. An old slower response that overwrites a newer one violates this property.

**Bug family B — stuck loading indicator.** Once a failed request has completed and an error has been surfaced, the loading indicator must not remain active. The fixture uses a visible loading message as the observable state.

**Control — normal success.** A successful single search shows the requested query and does not leave the loading indicator active.

These are fixture-specific oracles. Real websites need careful specification of legitimate UI behavior to avoid false positives.

## 4. Implementation roadmap

1. **Harness (implemented):** Local buggy/fixed fixtures; deterministic failure and response delay; Playwright browser-based tests, JSON evidence export.
2. **Baseline B0:** Random or predefined interaction sequence generation under a fixed test budget.
3. **Baseline B1:** Explicit code heuristics to identify request/response updates and error-handling paths, followed by browser checks.
4. **Proposed B2:** LLM generates candidate interaction/failure sequences from bounded snippets or DOM information. Validate each sequence against a strict schema before executing. No LLM may set the pass/fail outcome; only browser-state oracles do.
5. **Generalization:** Independent benchmark of intentionally seeded and authentic open-source issue/fix pairs. Separate tuning from held-out evaluation projects.

## 5. Evaluation design

- **Dataset:** Start with two known seeded bug families. Grow toward multiple independently sourced apps, versions, and bug/fix pairs. Record provenance, licenses, commits, and severity.
- **Unit of evaluation:** A distinct labeled bug/fix pair, not merely a repeated test run.
- **Metrics:** Per-bug detection recall, precision / false-positive rate where negative examples are included, unique bugs found per 100 tests, elapsed browser time, LLM API/token cost, and test stability.
- **Fairness:** Keep identical browser environments and total test/execution budgets. Use several LLM seeds and multiple repeats to handle stochastic behavior.
- **Ablations:** No AI, no source heuristic, no deterministic oracle, all components.
- **Threats to validity:** Seeded-bug overfitting, oracle assumptions, training-data contamination, prompt sensitivity, and framework-specific behavior.

## 6. Existing related work (do not claim novelty yet)

- Liu et al., **WEFix**, WWW 2024: fixes flaky end-to-end UI tests with dynamically inferred waits. Related through asynchronous timing, but the task differs from finding application logic errors. DOI: https://doi.org/10.1145/3589334.3645628
- Pei et al., **Non-Flaky and Nearly-Optimal Time-based Treatment of Asynchronous Wait Web Tests**, ACM TOSEM, 2024: studies and repairs asynchronous wait flakiness. DOI: https://doi.org/10.1145/3695989
- Li et al., **Large Language Models for Automated Web-Form-Test Generation: An Empirical Study**, ACM TOSEM, published 2026: evaluates LLMs for web-form test generation. DOI: https://doi.org/10.1145/3735553
- Playwright documentation, https://playwright.dev/python/docs/network : browser network interception and deterministic mocking can support controlled testing.

We still need a systematic related-work search explicitly focused on **client-side async state consistency**, **race-aware web UI test generation**, and **LLM-assisted UI bug detection**, to establish the genuine gap.

## 7. Expected outcomes, without overclaiming

A reproducible harness, baseline tests, error analysis, and a manuscript **only if** an evidence-backed contribution emerges. A one-week pilot is realistic; a top-conference submission will require substantially more validation.

## 8. Draft paper skeleton

1. Introduction (problem, current limitations, research questions)
2. Related Work (web testing, flaky tests, AI test generation)
3. Background and Bug Model (asynchronous events and UI invariants)
4. Approach (candidate generation + verification)
5. Experimental Setup (benchmarks, baselines, budgets)
6. Results (populate from measured experiments only)
7. Discussion and Threats to Validity
8. Conclusion
