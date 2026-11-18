/*
 * WebStateCheck Day 5 — independently documented asynchronous validation race.
 * IMPORTANT: This imports the ACTUAL bundled source code from final-form at
 * a pinned upstream Git commit. No library implementation is mocked here.
 * The validator / test inputs are deliberately controlled by this probe.
 * Reference: https://github.com/final-form/final-form/issues/509
 * Fix:       https://github.com/final-form/final-form/pull/513
 */
'use strict';
const path = require('node:path');
const fs = require('node:fs');

const [artifact, label, commit] = process.argv.slice(2);
if (!artifact || !label || !commit || !fs.existsSync(artifact)) {
  console.error('Usage: node probe.cjs <bundled-module.cjs> <before|after> <commit-sha>');
  process.exit(2);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
function fieldView(form) {
  const state = form.getFieldState('email');
  return state ? {
    value: state.value === undefined ? null : state.value,
    validating: state.validating,
    error: state.error === undefined ? null : String(state.error)
  } : null;
}

async function run() {
  const { createForm } = require(path.resolve(artifact));
  if (typeof createForm !== 'function') {
    throw new Error('Bundled upstream index does not export createForm');
  }
  const queue = [];
  const events = [];
  const validator = value => new Promise(resolve => queue.push({ value, resolve }));
  const form = createForm({ onSubmit: () => {} });
  const unsubscribe = form.registerField(
    'email',
    state => events.push({
      value: state.value === undefined ? null : state.value,
      validating: state.validating,
      error: state.error === undefined ? null : String(state.error)
    }),
    { value: true, validating: true, error: true },
    { getValidator: () => validator, validateFields: [] }
  );

  // Registration itself may start validation: settle it before measuring.
  for (const p of queue.splice(0)) p.resolve(undefined);
  await sleep(20);

  // Two overlapping validations. Resolve the earlier request first.
  form.change('email', 'first');
  form.change('email', 'second');
  const first = queue.find(p => p.value === 'first');
  const second = queue.find(p => p.value === 'second');
  if (!first || !second) {
    throw new Error(`Probe setup failed: expected 'first' and 'second' validators, got ${JSON.stringify(queue.map(p => p.value))}`);
  }
  const whileBothPending = fieldView(form);
  first.resolve('outdated validation error');
  await sleep(25);
  const afterFirstResolves = fieldView(form);
  second.resolve(undefined);
  await sleep(25);
  const afterSecondResolves = fieldView(form);

  const result = {
    source: 'final-form/final-form',
    label,
    upstream_commit: commit,
    document_issue: 'https://github.com/final-form/final-form/issues/509',
    fix_pr: 'https://github.com/final-form/final-form/pull/513',
    scenario: 'overlapping async validators; first resolves while second is pending',
    both_pending: whileBothPending,
    after_older_resolved: afterFirstResolves,
    after_latest_resolved: afterSecondResolves,
    violation: afterFirstResolves?.validating === false,
    note: 'Violation means field.validating=false while newer validation is still pending.',
    event_count: events.length
  };
  if (unsubscribe) unsubscribe();
  console.log(JSON.stringify(result, null, 2));
}
run().catch(error => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
