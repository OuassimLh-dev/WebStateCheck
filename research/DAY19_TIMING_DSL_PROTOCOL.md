# Day 19 — Development action-grammar extension and controls

**Classification: known-issue development experiment. No blind test generation or autonomous detection.**

## Day 18 evidence driving this change

The user reproduced the documented upstream `p-queue` issue #256 with three repeats on each pinned revision. In `sync_self_abort`, the original revision left the first task pending and blocked the next task, whereas the fixed revision rejected it and started the next task. Microtask, external-abort and no-abort controls behaved as expected. The earlier Day 17 exhaustive matrix showed no revision differences, because its runner could only cancel **externally** after submission. This is a demonstrated expressiveness gap, not an AI success.

## Day 19 parameterized timing plan

The new plans are JSON data, not four hard-coded Node branches or patch-specific logic. The public task-profile parameters are:

- `first_task`: `gated` or `immediate`, determining whether the first task returns a held promise or an immediately fulfilled value.
- `abort_timing`: `none`, `in_callback_sync`, `in_callback_microtask`, or `after_submit_external`.
- A second quick task is always submitted to observe whether the queue makes progress.
- Each plan constructs a fresh `p-queue({concurrency:1})`, its own `AbortController`, and a held gate. The same bounded observation occurs before any cleanup. Source files are never patched.

The eight included plans cover the Cartesian product of two task profiles and four timing modes. Plans are strictly validated; malformed IDs, private source labels, unexpected fields and unsupported behavior are rejected. Both source revisions receive exactly the same plan data. The built source revisions and SHA-256 build provenance are verified via the Day 18/15 checks, and the Day 11 lock is verified before and after execution.

**Budget caveat:** Every plan issues two queue submissions, but `after_submit_external` adds an explicit abort call. Callback scheduling differs as well. Therefore equal queue submission counts **do not** constitute equal mutation, generation, or execution budgets. No AI-vs-random-vs-heuristic comparison is made here.

## Interpretation

- Report all observable revision differences, including error strings, but treat them as *diagnostic leads*, not automatically independent bugs.
- Compare the four `gated` cases on shared fields to saved Day 18 observations when the observe windows match; agreement is a regression check, not independent validation.
- Do not modify the nine frozen Day 11 files, the staged original two-action public specification, or the upstream library.
- Do not seal target `t01`, whose issue has been inspected in this conversation.
- A future genuine holdout needs a **target-independent** action grammar and explicit budget rules (including callback-body complexity, cancellation actions, observation and generation time), isolated generation context, frozen target selection, predeclared oracles and review of unique issues.

## Next milestone

After verifying the parameterized runner on the user's Mac, write a separate versioned protocol amendment proposal for new targets, then choose *new* independent software without using its historical fix as prompt context. Do not retroactively change the old study design.
