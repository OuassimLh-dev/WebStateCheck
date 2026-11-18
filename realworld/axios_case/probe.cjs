'use strict';
// Isolated module-level reproduction using UNMODIFIED upstream CancelToken.js.
// Stub only CanceledError's constructor, not the cancellation implementation.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');

function loadCancelToken(filename) {
  const absolute = path.resolve(filename);
  const mod = new Module(absolute, module);
  mod.filename = absolute;
  mod.paths = Module._nodeModulePaths(path.dirname(absolute));
  mod.require = function (name) {
    if (name === './CanceledError') {
      return class CanceledError extends Error {
        constructor(message) { super(message || 'canceled'); this.name = 'CanceledError'; }
      };
    }
    throw new Error(`Unexpected dependency imported by upstream file: ${name}`);
  };
  mod._compile(fs.readFileSync(absolute, 'utf8'), absolute);
  return mod.exports;
}

async function exercise(CancelToken, scenario) {
  const source = CancelToken.source();
  const notified = [];
  const count = 5;
  const listeners = [];
  for (let i = 0; i < count; i++) {
    const listener = () => {
      notified.push(i);
      if (scenario === 'unsubscribe_during_notification') {
        source.token.unsubscribe(listeners[i]);
      }
    };
    listeners.push(listener);
    source.token.subscribe(listener);
  }
  const errors = [];
  const onUnhandled = error => errors.push({name: error && error.name, message: String(error && error.message)});
  process.on('unhandledRejection', onUnhandled);
  try {
    source.cancel('cancel all');
    // Allow the original Promise callback to run, and the unhandledRejection
    // event (if any) to surface. This is a controlled probe, not a speed test.
    await new Promise(resolve => setTimeout(resolve, 50));
  } finally {
    process.removeListener('unhandledRejection', onUnhandled);
  }
  return {
    scenario,
    cancellation_requested: true,
    registered_listener_count: count,
    notified_listener_ids: notified,
    all_listeners_notified: notified.length === count && new Set(notified).size === count,
    unhandled_rejections: errors,
    unexpected_exception: errors.length > 0,
  };
}

async function main() {
  const [filename, label, sha, scenario] = process.argv.slice(2);
  if (!filename || !['before', 'after'].includes(label) || !/^[0-9a-f]{40}$/.test(sha || '') ||
      !['unsubscribe_during_notification', 'stable_listeners'].includes(scenario)) {
    throw new Error('Usage: node probe.cjs <source> <before|after> <40-char SHA> <scenario>');
  }
  const CancelToken = loadCancelToken(filename);
  const result = await exercise(CancelToken, scenario);
  process.stdout.write(JSON.stringify({...result, label, upstream_commit: sha}) + '\n');
}
main().catch(e => { console.error(e); process.exitCode = 2; });
