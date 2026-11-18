// Day 18 -- known-issue coverage-gap diagnostic, NOT a blind benchmark.
// Probe only public p-queue APIs; pinned upstream files are never changed.
// Receives a JSON request from stdin; returns only observations from the given compiled build.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const modulePath = process.argv[2];
if (!modulePath) throw new Error('Usage: node day18_abort_probe.mjs <p-queue/dist/index.js>');
const {default: PQueue} = await import(pathToFileURL(resolve(modulePath)).href);
if (typeof PQueue !== 'function') throw new Error('p-queue default export must be callable');
const input = JSON.parse(readFileSync(0, 'utf8'));
if (!Array.isArray(input.case_ids) || !Number.isInteger(input.observe_ms)
    || input.observe_ms < 10 || input.observe_ms > 2000) {
  throw new Error('Expected case_ids and observe_ms between 10 and 2000');
}
const supported = new Set(['sync_self_abort', 'microtask_self_abort', 'external_abort', 'no_abort_control']);
if (new Set(input.case_ids).size !== input.case_ids.length
    || input.case_ids.some(id => !supported.has(id))) throw new Error('Unrecognized or duplicate case');

async function runCase(caseId, observeMs) {
  const queue = new PQueue({concurrency: 1});
  const controller = new AbortController();
  const abortReason = new Error('day18-diagnostic-cancel');
  let openGate;
  const gate = new Promise(resolve => { openGate = resolve; });
  let firstStatus = 'pending';
  let firstError = null;
  let nextStarted = false;
  let nextStatus = 'pending';
  const errors = [];
  queue.on('error', error => errors.push(String(error?.message ?? error)));
  const first = queue.add(() => {
    if (caseId === 'sync_self_abort') {
      // The historical timing: an abort occurs during the task callback,
      // before queue.add has finished registering its running listener.
      controller.abort(abortReason);
    } else if (caseId === 'microtask_self_abort') {
      queueMicrotask(() => controller.abort(abortReason));
    }
    return gate;
  }, {signal: controller.signal});
  // Synchronous handlers prevent unhandled rejections in the diagnostic.
  first.then(
    () => { firstStatus = 'fulfilled'; },
    error => { firstStatus = 'rejected'; firstError = String(error?.message ?? error); },
  );
  const next = queue.add(() => { nextStarted = true; return 'next-task-result'; });
  next.then(
    () => { nextStatus = 'fulfilled'; },
    () => { nextStatus = 'rejected'; },
  );
  if (caseId === 'external_abort') controller.abort(abortReason);

  // Same observation wait on all cases and both source revisions.
  await sleep(observeMs);
  const observed = {
    case_id: caseId,
    first_status: firstStatus,
    first_error: firstError,
    next_started: nextStarted,
    next_status: nextStatus,
    signal_aborted: controller.signal.aborted,
    queue_pending: queue.pending,
    queue_size: queue.size,
    queue_error_events: [...errors],
  };
  // The explicit gate is released only AFTER the observation. This keeps the
  // old revision from hanging, without disguising its pre-release state.
  openGate('gate-released');
  const cleanup = await Promise.race([
    Promise.allSettled([first, next]).then(() => 'finished'),
    sleep(2000).then(() => 'timeout'),
  ]);
  queue.clear();
  return {...observed, cleanup};
}
const cases = [];
for (const id of input.case_ids) cases.push(await runCase(id, input.observe_ms));
process.stdout.write(JSON.stringify({cases}) + '\n');
