# Day 22 — Predefined diagnostic of timing/profile interaction

**Classification:** development-only, known historical `p-queue` issue. Not AI
performance, a preregistered held-out evaluation, or a confirmed unique-defect count.

## Why

The Day 21 pairings have matched marginal costs and timings but different *joint*
timing × subject-completion distributions. If a defect is specific to one pair,
which method receives that pair can drive apparent results more than test strategy.

## Existing evidence audit

First load Day 21 output. Verify current Day 20 plan hashes and the Day 21 runner
SHA-256, revalidate 32 scenario executions and their recorded resource counters,
and recompute Day 21's saved analysis before producing the confound table. Report
changed repeated executions separately from distinct scenario IDs and distinct
factorial cells. No defect label is inferred from an observed revision difference.

## Factorial development run

- Source: the same two source-pinned `p-queue` bundles used in Day 21, unchanged.
- Design: 4 cancellation timing modes × 2 first-task completion profiles = 8 cells.
- Fold A: exactly the existing Day 20 random method's four pairings (renamed IDs).
- Fold B: same timing order, with the held/immediate profile flipped for each row.
- Each fold: 4 scenarios, 8 queue submissions, 3 aborts, 1 microtask schedule,
  4 passive snapshots, and a 50-ms nominal observation window per scenario.
- Each cell: fresh single-concurrency queue, one subject task + progress probe.
- Run: 2 folds × 4 scenarios × 2 versions × 2 repeats = 32 executions.
- Pre-cleanup snapshot and afterward gate release; require successful cleanup.
- Instrumentation: reuse Day 21 source-pinned JS adapter without modification.
- Main observations: first task status, progress probe start, queue fields,
  and event logs. Count before/after differing cells and repeat instability.
- No result-driven selection, schema alteration, source modification, or baseline
  plan replacement. Plan hashes are sealed in a new **development** manifest.

This fully crosses two *already-known dimensions*; it does not test autonomous
scenario generation or hypothesis discovery. The two folds **are not** competing
methods, and no inferential superiority claim should be drawn from them.

## Important limitations

The case was selected with prior knowledge of the historical issue. This diagnostic
cannot be made blinded retroactively. A future comparison needs a separately versioned
v2 protocol, new independently chosen target(s), oracle review, isolated model
prompts, recorded selection costs, and actual independent defect adjudication.

Day 11's nine locked files and the staged `t01` packet are left unchanged.
**Do not seal t01.**
