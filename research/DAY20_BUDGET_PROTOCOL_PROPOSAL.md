# Day 20 — Proposed version 2 timing vocabulary and semantic-cost ledger

**Status: PROPOSAL / DEVELOPMENT ONLY.** This document is additive. It does not alter the nine Day 11 frozen files or the unsealed Day 13 `t01` packet. Day 19 is not retrospectively relabeled as a held-out study.

## Motivation based on development evidence

Day 17's static grammar could not express synchronous self-cancellation during task startup. Day 18 reproduced the known p-queue issue under this particular timing. Day 19 generalized the timing parameter and reproduced the difference in one of eight development plans, but the `after_submit_external` mode uses a distinct external API call, meaning equal *queue-submission counts* did not imply equal mutation budgets. It also already incorporated knowledge of the historical defect. A defensible comparison needs a domain-portable, frozen vocabulary and transparent accounting before new target selection.

## Scope and proposal schema

The version-2 proposal covers **abortable promise/task queue APIs** only. It is NOT automatically portable to DOM applications, HTTP services, or arbitrary JavaScript state machines. A target adapter must map this vocabulary to documented, observable public behavior and justify any semantic differences.

A plan includes precisely two submitted tasks: a subject task with an abort signal and a quick progress probe. The subject's completion profile is `held` or `immediate`. `held` means completion is blocked until an explicit cleanup/release *after* the observation; `immediate` means the body completes promptly. Timing mode is one of:

- `callback_sync`: abort the subject's signal synchronously inside the task callback.
- `callback_microtask`: schedule the subject's abort in a microtask inside the callback.
- `external_after_submit`: abort the subject signal externally after task submission.
- `none`: do not abort the subject signal.

The runner must produce the same passive snapshot after all planned actions and **before** releasing any deliberately held gates; post-snapshot cleanup cannot silently change a verdict. The observation window in the sample protocol is 50ms and the per-scenario timeout 5000ms. These are proposed values, not universally safe/adequate settling criteria. Real targets may need a separately justified preregistered revision.

## Resource accounting — matching more than nominal actions

Every method's four-scenario *sample packet* must contain all four timing modes once and exactly two `held` and two `immediate` subject profiles. The static budget vector per method is:

| Semantic resource | Count |
|---|---:|
| Scenarios | 4 |
| Task submissions | 8 |
| Abort calls (including callback-side) | 3 |
| Callback-side abort calls | 2 |
| External abort calls | 1 |
| Microtask schedules | 1 |
| Held subject tasks | 2 |
| Immediate subject tasks | 2 |
| Passive pre-cleanup snapshots | 4 |
| Nominal observation window | 200ms aggregate |

Each semantic effect is counted even if it occurs *inside* a callback rather than as an explicit user action. Microtask scheduling is accounted separately. No operation is “free” merely because it was supplied as task-body behavior. Plan generation retries, prompt tokens, input length, model latency, browser/Node execution wall-clock, and cleanup times must also be logged in future evaluations, rather than collapsed into this static ledger.

**Caveat:** Equal cost vectors do not prove equal effort or equivalent detectability. Joint profile/timing allocations vary. Formal effectiveness must be tested on multiple genuinely new targets, with proper effect-size and uncertainty reporting.

## Research separation

- The **random** sample plan is a deterministic seeded shuffle of timing modes and subject profiles.
- The **heuristic** sample plan is a hand-authored, development-informed ordering. It is NOT an independent baseline unaffected by p-queue knowledge.
- No actual **LLM** candidate is generated in this conversation. For future study, isolate the generation context and freeze the full input prompt, model/version, settings, outputs, generation date, decoding and retry policy, plus token and time costs.
- No `before`/`after` revision labels, upstream issue references, source commit IDs or private truth enter the plan JSON schema. An independent human must still review the public target packet for leakage.
- The validator checks JSON format and **budget feasibility**, not downstream behavior, bug-detection correctness, instrumented concurrency, or target-specific API conformance.
- Do not claim t01 is held out, do not seal it, and do not update or overwrite the nine frozen Day 11 entries.

## What remains before a genuinely new cohort

1. Implement and test a domain-adapter conformance suite (task ordering, signal timing, fixed-window snapshots, post-observation cleanup, repeat stability and timeout classification) on fresh non-scored examples.
2. Decide whether the four-scenario/2-submission budget has adequate statistical power and legitimate target coverage; version changes before any new target selection.
3. Select truly new independent targets with independently documented contracts and fixes. Separate their private truth from the entire test-generator context.
4. Register all eligible targets, protocol, oracle specifications, model/generator settings, cost quotas and evaluation criteria **before** running candidates; retain exclusion and failure logs.
5. Perform a multi-project, paired comparison with validation of unique confirmed defects; report false alerts and inconclusives without claiming every revision difference is a bug.
