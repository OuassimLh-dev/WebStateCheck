/**
 * Logic-level JavaScript harness that works without Chromium.
 * IMPORTANT: Simulates DOM and fetch; does NOT replace real browser testing.
 * Run: node tests/js_logic_harness.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..');
const SOURCE = fs.readFileSync(path.join(ROOT, 'fixtures', 'app.js'), 'utf8');

function makeApp(mode) {
  const elements = {};
  for (const id of ['#query', '#search', '#status', '#error', '#results']) {
    elements[id] = {
      value: '', textContent: '', handlers: {},
      addEventListener(name, cb) { this.handlers[name] = cb; },
    };
  }
  const pending = [];
  const fetch = (url) => new Promise(resolve => {
    const query = new URL(url, 'http://localhost').searchParams.get('q');
    pending.push({query, resolve});
  });
  const window = { location: {search: `?mode=${mode}`} };
  const document = { querySelector: id => elements[id] };
  const context = vm.createContext({URLSearchParams, window, document, fetch});
  vm.runInContext(SOURCE, context, {filename: 'fixtures/app.js'});
  return {
    elements, pending, window,
    click(query) { elements['#query'].value = query; elements['#search'].handlers.click(); },
    respond(query, {error = false} = {}) {
      const index = pending.findIndex(r => r.query === query);
      assert(index >= 0, `Unseen request for ${query}`);
      const [request] = pending.splice(index, 1);
      request.resolve(error ? {ok:false, status:503} : {ok:true, json:async()=>({query})});
    },
  };
}
const settle = () => new Promise(resolve=>setImmediate(resolve));

async function runCase(mode, caseName) {
  const app = makeApp(mode);
  if (caseName === 'stale_response') {
    app.click('old');
    app.click('new');
    app.respond('new'); await settle();
    app.respond('old'); await settle();
    const actual = app.elements['#results'].textContent;
    return { violation_detected: actual !== 'Results for: new', evidence: {actual_results: actual} };
  }
  if (caseName === 'stuck_loading') {
    app.click('fail');
    app.respond('fail', {error:true}); await settle();
    const status = app.elements['#status'].textContent;
    const error = app.elements['#error'].textContent;
    return { violation_detected: !!status.trim(), evidence: {loading_text_after_failure:status, error_text:error} };
  }
  if (caseName === 'normal_success') {
    app.click('hello');
    app.respond('hello'); await settle();
    const results = app.elements['#results'].textContent;
    const status = app.elements['#status'].textContent;
    return { violation_detected: results !== 'Results for: hello' || !!status.trim(), evidence: {results, loading_text: status} };
  }
  throw new Error(`Unsupported ${caseName}`);
}

(async () => {
  const rows = [];
  for (const mode of ['buggy','fixed']) {
    for (const caseName of ['stale_response','stuck_loading','normal_success']) {
      const actual = await runCase(mode, caseName);
      const expected = mode === 'buggy' && caseName !== 'normal_success';
      const as_expected = actual.violation_detected === expected;
      rows.push({mode, case:caseName, expected_violation:expected, ...actual, as_expected});
      console.log(`[${as_expected?'PASS':'FAIL'}] ${mode} ${caseName}: violation=${actual.violation_detected}`);
    }
  }
  const result = {
    source: 'JavaScript VM logic-only simulation (not a browser)',
    timestamp_utc: new Date().toISOString(),
    correct: rows.filter(r=>r.as_expected).length,
    total: rows.length,
    observations: rows,
  };
  fs.mkdirSync(path.join(ROOT, 'results'), {recursive:true});
  fs.writeFileSync(path.join(ROOT, 'results', 'js_logic_observations.json'), JSON.stringify(result,null,2)+'\n');
  console.log(`${result.correct}/${result.total} logic checks match expected seeded fixture behavior`);
  if (result.correct !== result.total) process.exitCode = 1;
})().catch(err=>{console.error(err);process.exitCode=1;});
