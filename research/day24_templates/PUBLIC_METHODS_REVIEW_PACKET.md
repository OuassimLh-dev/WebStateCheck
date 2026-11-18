# WebStateCheck — Public methodology review packet (DRAFT)

**Audience:** independent research-methods reviewer. **Not an LLM generator prompt.**

## Proposed scope and question

For third-party, abortable asynchronous JavaScript task queues, do LLM-proposed testing programs find more *uniquely confirmed* asynchronous correctness defects than conventional heuristics and seeded random generation, given the same testing opportunities and predeclared cost ceilings?

This is intentionally **not** a claim about arbitrary websites or all JavaScript software.

## Proposed three methods

- **Random:** seeded generation over a published task-program grammar, rejecting invalid programs according to a preregistered retry policy.
- **Non-LLM heuristic:** deterministic generator over the *same* public grammar, built and frozen before new target outcomes are inspected.
- **LLM:** isolated model context receiving only the approved, target-specific public contract, grammar, budget and output schema. Preserve the exact prompt, version, settings, raw outputs, retries, token usage and generation time.

## Preliminary design choices requiring review

- **Primary:** equal ceilings for number of candidate scenarios, API mutations, callback-side and external cancellations, microtask operations, observation windows and total execution time. Actual utilization is recorded. Strategies should be free to choose their timing/profile combinations subject to one shared predeclared grammar.
- **Secondary:** a fixed factorial or stratified analysis to separate scheduling-window coverage from task-profile effects. Do not confuse a cell-completion design with an effectiveness comparison.
- **Paired evaluation:** each target is tested by all methods with identical setup, reset and observation policies; seeds/repeats and method order are fixed before inspection.
- **Unit of evidence:** target-level unique confirmed defects, **not** repeats, number of alerts, or before/after mismatches.

A reviewer must choose actual numeric ceilings, sample size, retry quota and primary estimand *before* target screening. Earlier development numbers are examples, not automatically valid for a new study.

## Proposed independent correctness procedure

For every target, a reviewer writes a behavior contract from publicly documented APIs, including task settlement, cancellation, progress, idle state and deliberately unfinished tasks when applicable. The oracle specifies exact clear / violation / inconclusive classifications and bounded observation rules. A revision difference is only a diagnostic lead. Independently review failed traces and deduplicate them into confirmed root causes.

## Required decisions before registration

1. Eligibility, recruitment channel, sample size and exclusion rules.
2. Source-independent oracle per target and adjudication of ambiguous traces.
3. Exact v2 action grammar, per-method budgets, retry limits and wall-clock rules.
4. Model isolation, prompt logging, baseline freeze, generation cost accounting.
5. No-leakage review for each model-facing target packet, private ground-truth isolation.
6. Versioned protocol approval by a named independent reviewer followed by an immutable hash manifest.

**Current status: UNREVIEWED. No prospective scoring is authorized by this packet.**
