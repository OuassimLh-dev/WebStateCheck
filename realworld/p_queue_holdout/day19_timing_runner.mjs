// Day 19 -- parameterized, development-only task-timing runner.
// Reads a public-data plan from stdin and the prebuilt pinned p-queue source as argv[2].
// NEVER reads an issue description, source revision label, or private truth metadata.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const modulePath = process.argv[2];
if (!modulePath) throw new Error('Usage: node day19_timing_runner.mjs <built-p-queue-index.js>');
const input = JSON.parse(readFileSync(0, 'utf8'));
const validTimings = new Set(['in_callback_sync', 'in_callback_microtask', 'after_submit_external', 'none']);
const validProfiles = new Set(['gated', 'immediate']);
if (input.schema_version !== 'wsc-timing-dev-v1' || input.target_id !== 't01'
    || !Number.isInteger(input.observe_ms) || input.observe_ms < 10 || input.observe_ms > 2000
    || !Array.isArray(input.plans) || input.plans.length < 1 || input.plans.length > 16) {
  throw new Error('Invalid or unsupported timing-runner payload');
}
const seen = new Set();
for (const plan of input.plans) {
  if (!plan || typeof plan !== 'object' || Object.keys(plan).sort().join(',') !== 'abort_timing,first_task,plan_id'
      || typeof plan.plan_id !== 'string' || !/^[a-z][a-z0-9-]{1,40}$/.test(plan.plan_id)
      || seen.has(plan.plan_id) || !validProfiles.has(plan.first_task) || !validTimings.has(plan.abort_timing)) {
    throw new Error('Invalid, duplicate, or unsupported timing plan');
  }
  seen.add(plan.plan_id);
}
const {default: PQueue} = await import(pathToFileURL(resolve(modulePath)).href);
if (typeof PQueue !== 'function') throw new Error('p-queue default export must be callable');

async function runPlan(plan, observeMs) {
  const queue = new PQueue({concurrency: 1});
  const controller = new AbortController();
  const reason = new Error('day19-development-abort');
  let release;
  const held = new Promise(resolveGate => { release = resolveGate; });
  let firstStatus = 'pending';
  let firstError = null;
  let nextStarted = false;
  let nextStatus = 'pending';
  const queueErrors = [];
  queue.on('error', err => queueErrors.push(String(err?.message ?? err)));

  // First task: two dimensions are supplied as DATA, not hand-selected branches
  // keyed to a historical before/after revision label.
  const first = queue.add(() => {
    if (plan.abort_timing === 'in_callback_sync') controller.abort(reason);
    if (plan.abort_timing === 'in_callback_microtask') {
      queueMicrotask(() => controller.abort(reason));
    }
    return plan.first_task === 'gated' ? held : 'immediate-first-result';
  }, {signal: controller.signal});
  first.then(
    () => { firstStatus = 'fulfilled'; },
    err => { firstStatus = 'rejected'; firstError = String(err?.message ?? err); },
  );
  const next = queue.add(() => {
    nextStarted = true;
    return 'second-task-result';
  });
  next.then(
    () => { nextStatus = 'fulfilled'; },
    () => { nextStatus = 'rejected'; },
  );
  if (plan.abort_timing === 'after_submit_external') controller.abort(reason);
  // Fixed bounded passive observation. No gate release before snapshot.
  await sleep(observeMs);
  const observed = {
    plan_id: plan.plan_id,
    first_task: plan.first_task,
    abort_timing: plan.abort_timing,
    first_status: firstStatus,
    first_error: firstError,
    next_started: nextStarted,
    next_status: nextStatus,
    signal_aborted: controller.signal.aborted,
    queue_pending: queue.pending,
    queue_size: queue.size,
    queue_error_events: [...queueErrors],
    task_submissions: 2,
    external_abort_mutations: Number(plan.abort_timing === 'after_submit_external'),
  };
  // Cleanup happens AFTER the observation. It is NOT scored as a user action.
  release('released-after-observation');
  const cleanup = await Promise.race([
    Promise.allSettled([first, next]).then(() => 'finished'),
    sleep(2000).then(() => 'timeout'),
  ]);
  queue.clear();
  return {...observed, cleanup};
}
const records = [];
for (const plan of input.plans) records.push(await runPlan(plan, input.observe_ms));
process.stdout.write(JSON.stringify({schema_version: input.schema_version, records}) + '\n');
