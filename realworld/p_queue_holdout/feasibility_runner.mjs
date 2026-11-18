// Day 15: real p-queue public API feasibility runner.
// It receives an already built pinned library and a public action plan via stdin.
// It knows nothing about issue numbers, historical patches, or which revision is buggy.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';

const modulePath = process.argv[2];
if (!modulePath) throw new Error('Usage: node feasibility_runner.mjs <p-queue/dist/index.js>');
const payload = JSON.parse(readFileSync(0, 'utf8'));
const {default: PQueue} = await import(pathToFileURL(resolve(modulePath)).href);
if (typeof PQueue !== 'function') throw new Error('Expected a p-queue default class export');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const makeDeferred = () => {
  let resolvePromise;
  const promise = new Promise(resolve => { resolvePromise = resolve; });
  return {promise, release: () => resolvePromise('released')};
};

async function runScenario(scenario, maxWaitMs) {
  const queue = new PQueue({concurrency: 1});
  const outcomes = [];
  const events = [];
  const delayed = [];
  let currentController;
  let active = 0;
  let maxActive = 0;
  let observedIdle;
  let taskNumber = 0;
  queue.on('error', error => events.push({type: 'queue_error', message: String(error.message ?? error)}));
  const register = (type, task, options = {}) => {
    const record = {id: ++taskNumber, type, status: 'pending'};
    outcomes.push(record);
    const handle = queue.add(async ({signal}) => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      try { return await task(signal); }
      finally { active -= 1; }
    }, options);
    // Attach handlers synchronously to avoid an unhandled rejection in the experiment harness.
    handle.then(value => { record.status = 'fulfilled'; record.value = String(value); },
      error => { record.status = 'rejected'; record.error = String(error?.message ?? error); });
  };
  for (const action of scenario.actions) {
    const key = `${action.type}:${action.target}`;
    if (key === 'submit:enqueue_quick_task') {
      register('quick', async () => 'quick-result');
    } else if (key === 'submit:enqueue_delayed_task') {
      const gate = makeDeferred();
      delayed.push({gate, released: false});
      register('delayed', async () => await gate.promise);
    } else if (key === 'submit:enqueue_rejecting_task') {
      register('rejecting', async () => {throw new Error('expected-rejection');});
    } else if (key === 'submit:enqueue_cancelable_task') {
      currentController = new AbortController();
      register('cancelable', async signal => {
        if (signal?.aborted) throw new Error('task-aborted');
        return await new Promise((resolveTask, rejectTask) => {
          const timer = setTimeout(() => resolveTask('cancelable-result'), 35);
          signal?.addEventListener('abort', () => {
            clearTimeout(timer);
            rejectTask(new Error('task-aborted'));
          }, {once:true});
        });
      }, {signal: currentController.signal});
    } else if (key === 'cancel:current_signal') {
      if (!currentController) throw new Error('cancel without a previous cancellable task');
      currentController.abort();
      events.push({type:'signal_cancelled'});
    } else if (key === 'click:release_delayed_task') {
      const next = delayed.find(item => !item.released);
      if (!next) throw new Error('release with no delayed task');
      next.released = true;
      next.gate.release();
    } else if (key === 'click:observe_idle_status') {
      observedIdle = {pending: queue.pending, size: queue.size};
    } else {
      throw new Error('Unrecognized action: ' + key);
    }
    // A consistent microtask checkpoint after each user action.
    await Promise.resolve();
  }
  // The post-action observation is NOT a budgeted user action and is identical for all plans.
  // It is not the same as asserting queue.onIdle() (which would hang on unreleased gates).
  const settleWaitMs = Math.min(120, maxWaitMs);
  await sleep(settleWaitMs);
  const unreleased = delayed.filter(item => !item.released).length;
  const pendingTaskRecords = outcomes.filter(task => task.status === 'pending').length;
  let status = 'settled';
  if (unreleased > 0) status = 'needs_release';
  else if (pendingTaskRecords > 0 || queue.pending > 0 || queue.size > 0) status = 'unresolved';
  const record = {plan_id: scenario.plan_id, actions: scenario.actions,
    status, pending_task_records: pendingTaskRecords, unreleased_gates: unreleased,
    queue_snapshot: {pending: queue.pending, size: queue.size, observed_idle: observedIdle ?? null},
    max_active: maxActive, outcomes: outcomes.map(t => ({...t})), events};
  // Delayed actions still pending are cleaned up AFTER observation, never recoded as passing.
  for (const item of delayed) if (!item.released) item.gate.release();
  queue.clear();
  await sleep(2);
  return record;
}
const records = [];
for (const scenario of payload.scenarios) {
  records.push(await runScenario(scenario, payload.max_wait_ms));
}
process.stdout.write(JSON.stringify({target_id: payload.target_id, records}) + '\n');
