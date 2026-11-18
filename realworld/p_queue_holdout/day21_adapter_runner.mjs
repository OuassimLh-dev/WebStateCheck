// Day 21: resource-instrumented, development-only adapter for the wsc async-schedule v2 proposal.
// Loads a source-pinned library bundle passed on the command line. Reads only the public plan
// on stdin; no historical truth, version labels, or issue descriptions are consulted.
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {performance} from 'node:perf_hooks';

const bundle = process.argv[2];
if (!bundle) throw new Error('Usage: node day21_adapter_runner.mjs <p-queue-bundle>');
const pack = JSON.parse(readFileSync(0, 'utf8'));
const timings = new Set(['callback_sync', 'callback_microtask', 'external_after_submit', 'none']);
if (pack?.schema_version !== 'wsc-async-schedule-v2-PROPOSAL' ||
    pack?.domain !== 'abortable_promise_queue' ||
    !Array.isArray(pack.scenarios) || pack.scenarios.length !== 4 ||
    pack?.observation?.snapshot_policy !== 'passive_after_actions_before_cleanup' ||
    pack.observation.observe_ms !== 50 || pack.observation.timeout_ms !== 5000) {
  throw new Error('Unsupported v2 development packet');
}
for (const plan of pack.scenarios) {
  if (!timings.has(plan?.abort_timing) || !Array.isArray(plan?.tasks) || plan.tasks.length !== 2 ||
      !['held', 'immediate'].includes(plan.tasks[0]?.completion) ||
      plan.tasks[0]?.role !== 'subject' || plan.tasks[0]?.abort_signal !== true ||
      plan.tasks[1]?.role !== 'progress_probe' ||
      plan.tasks[1]?.completion !== 'immediate' || plan.tasks[1]?.abort_signal !== false) {
    throw new Error('Malformed scenario; run Python plan validator first');
  }
}
const {default: PQueue} = await import(pathToFileURL(resolve(bundle)).href);
if (typeof PQueue !== 'function') throw new Error('Expected default-exported PQueue constructor');

function safeError(error) { return String(error?.message ?? error); }

async function runOne(plan, observation) {
  const queue = new PQueue({concurrency: 1});
  const controller = new AbortController();
  const reason = new Error('day21-development-abort');
  const counters = {submissions: 0, abort_calls: 0, callback_abort_calls: 0,
    external_abort_calls: 0, microtask_schedules: 0, passive_snapshots: 0};
  const events = [];
  let firstStatus = 'pending';
  let secondStatus = 'pending';
  let firstError = null;
  let secondStarted = false;
  let firstStarted = false;
  let release;
  const held = new Promise(resolveGate => { release = resolveGate; });
  const queueErrors = [];
  queue.on('error', error => { queueErrors.push(safeError(error)); });

  const cancel = origin => {
    counters.abort_calls += 1;
    if (origin === 'callback') counters.callback_abort_calls += 1;
    else counters.external_abort_calls += 1;
    events.push('abort_' + origin);
    controller.abort(reason);
  };
  counters.submissions += 1;
  const first = queue.add(() => {
    firstStarted = true;
    events.push('first_started');
    if (plan.abort_timing === 'callback_sync') cancel('callback');
    if (plan.abort_timing === 'callback_microtask') {
      counters.microtask_schedules += 1;
      queueMicrotask(() => cancel('callback'));
    }
    return plan.tasks[0].completion === 'held' ? held : 'immediate-first';
  }, {signal: controller.signal});
  first.then(() => { firstStatus = 'fulfilled'; }, error => {
    firstStatus = 'rejected'; firstError = safeError(error);
  });
  counters.submissions += 1;
  const second = queue.add(() => {
    secondStarted = true;
    events.push('second_started');
    return 'second-result';
  });
  second.then(() => { secondStatus = 'fulfilled'; }, () => { secondStatus = 'rejected'; });
  if (plan.abort_timing === 'external_after_submit') cancel('external');

  const clock = performance.now();
  await new Promise(resolveSleep => setTimeout(resolveSleep, observation.observe_ms));
  const elapsed = performance.now() - clock;
  counters.passive_snapshots += 1;
  const snapshot = {
    first_started: firstStarted,
    first_status: firstStatus,
    first_error: firstError,
    second_started: secondStarted,
    second_status: secondStatus,
    signal_aborted: controller.signal.aborted,
    queue_pending: queue.pending,
    queue_size: queue.size,
    queue_error_events: [...queueErrors],
    events_before_snapshot: [...events],
  };
  // Instrumentation is frozen along with the snapshot. Cleanup is separated from observation.
  const resources = {...counters};
  release('released-post-snapshot');
  let timeoutId;
  const cleanup = await Promise.race([
    Promise.allSettled([first, second]).then(() => 'finished'),
    new Promise(resolveTimeout => { timeoutId = setTimeout(() => resolveTimeout('timeout'),
      Math.min(observation.timeout_ms, 2500)); }),
  ]);
  clearTimeout(timeoutId);
  queue.clear();
  return {
    plan_id: plan.plan_id,
    abort_timing: plan.abort_timing,
    subject_completion: plan.tasks[0].completion,
    resources,
    observe_elapsed_ms: Math.round(elapsed * 1000) / 1000,
    snapshot,
    cleanup,
  };
}

const records = [];
for (const plan of pack.scenarios) records.push(await runOne(plan, pack.observation));
process.stdout.write(JSON.stringify({schema_version: pack.schema_version, method: pack.method, records}) + '\n');
