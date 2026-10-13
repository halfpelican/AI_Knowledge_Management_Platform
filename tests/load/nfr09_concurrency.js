import http from 'k6/http';
import exec from 'k6/execution';
import { sleep, check } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import {
  BASE_URL, QUESTIONS, loginOnce, nextQuestion, ask,
  isValidReply, wasAnswered, runWasValid,
} from './common.js';

const MAX_DEGRADATION = 0.25;
const CONCURRENT_USERS = 20;
const BASELINE_ITERATIONS = Number(__ENV.BASELINE_ITERATIONS || 50);

const askBaselineMs = new Trend('ask_baseline_ms', true);
const askLoadMs = new Trend('ask_load_ms', true);
const uploadBaselineMs = new Trend('upload_baseline_ms', true);
const uploadLoadMs = new Trend('upload_load_ms', true);
const answeredRate = new Rate('answered_rate');

export const options = {
  scenarios: {
    // Phase 1: one user, a fixed number of rounds (stable, repeatable baseline).
    baseline: {
      executor: 'per-vu-iterations',
      exec: 'baseline',
      vus: 1,
      iterations: BASELINE_ITERATIONS,
      maxDuration: '15m',
      startTime: '0s',
      gracefulStop: '5m',
    },
    // Phase 2: 20 users. Starts after the baseline's maxDuration (15m) plus
    // its gracefulStop (5m), so the two phases can never overlap.
    load: {
      executor: 'constant-vus',
      exec: 'load',
      vus: CONCURRENT_USERS,
      duration: '10m',
      startTime: '20m',
      gracefulStop: '5m',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)'],
  thresholds: {
    'http_req_failed{name:ask}': ['rate<0.01'],
    'http_req_failed{name:upload}': ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  const cookies = loginOnce();
  // Untimed warm-up, tagged 'warmup' so it is not counted as a measured ask.
  ask(cookies, QUESTIONS[0], 'warmup');
  ask(cookies, QUESTIONS[0], 'warmup');
  return cookies;
}

const PARAGRAPH =
  'This is a load test document. It describes how the office kitchen roster works, ' +
  'who is responsible for cleaning the shared fridge on Fridays, how to report a ' +
  'broken appliance to facilities, and where spare supplies such as paper towels ' +
  'and dishwasher tablets are stored. Staff are asked to label their food, remove ' +
  'old items weekly, and wipe down benches after use. Questions about this roster ' +
  'should go to the facilities team. ';

// Every upload needs unique bytes: duplicates are matched by content hash and
// refused with 409 before any ingestion runs.
function uploadDocument(cookies) {
  const unique = `${exec.vu.idInTest}_${exec.scenario.iterationInTest}_${Date.now()}`;
  const body = PARAGRAPH.repeat(3) + `\nUnique reference: ${unique}\n`;
  return http.post(
    `${BASE_URL}/api/documents`,
    {
      file: http.file(body, `loadtest_${unique}.txt`, 'text/plain'),
      title: `Load test ${unique}`,
      department: 'LoadTest',
    },
    {
      // No Content-Type header: k6 sets the multipart boundary itself.
      headers: { 'X-CSRFToken': cookies.csrftoken },
      cookies,
      tags: { name: 'upload' },
      timeout: '300s',
    }
  );
}

function oneRound(cookies, askTrend, uploadTrend) {
  const askRes = ask(cookies, nextQuestion());
  const askOk = check(askRes, { 'ask returned 200 with documented shape': isValidReply });
  const answered = wasAnswered(askRes);
  answeredRate.add(answered);
  // Answered replies only: a no-answer reply skips generation and is faster.
  if (askOk && answered) {
    askTrend.add(askRes.timings.duration);
  }

  const upRes = uploadDocument(cookies);
  const upOk = check(upRes, { 'upload returned 201': (r) => r.status === 201 });
  if (upOk) {
    uploadTrend.add(upRes.timings.duration);
  }
  sleep(1);
}

export function baseline(cookies) {
  oneRound(cookies, askBaselineMs, uploadBaselineMs);
}

export function load(cookies) {
  oneRound(cookies, askLoadMs, uploadLoadMs);
}

export function handleSummary(data) {
  const p90 = (name) => (data.metrics[name] ? data.metrics[name].values['p(90)'] : null);
  const count = (name) => (data.metrics[name] ? data.metrics[name].values.count : 0);

  function compare(baseName, loadName) {
    const base = p90(baseName);
    const loaded = p90(loadName);
    if (!base || !loaded) {
      return { baseline_p90_ms: base, load_p90_ms: loaded, degradation_percent: null, pass: false };
    }
    const ratio = loaded / base;
    return {
      baseline_p90_ms: base,
      load_p90_ms: loaded,
      degradation_percent: Number(((ratio - 1) * 100).toFixed(1)),
      pass: ratio <= 1 + MAX_DEGRADATION,
    };
  }

  const askResult = compare('ask_baseline_ms', 'ask_load_ms');
  const uploadResult = compare('upload_baseline_ms', 'upload_load_ms');

  const uploadErrorsOk =
    data.metrics['http_req_failed{name:upload}']?.thresholds?.['rate<0.01']?.ok === true;
  const valid = runWasValid(data) && uploadErrorsOk;
  const haveData = askResult.baseline_p90_ms && askResult.load_p90_ms &&
                   uploadResult.baseline_p90_ms && uploadResult.load_p90_ms;

  const verdict = !haveData ? 'NO DATA'
    : !valid ? 'INVALID RUN'
    : askResult.pass && uploadResult.pass ? 'PASS'
    : 'FAIL';

  const report = {
    requirement: 'NFR-09',
    verdict,
    run_valid: valid,
    max_allowed_degradation_percent: MAX_DEGRADATION * 100,
    concurrent_users: CONCURRENT_USERS,
    ask: {
      ...askResult,
      baseline_samples: count('ask_baseline_ms'),
      load_samples: count('ask_load_ms'),
    },
    upload: {
      ...uploadResult,
      baseline_samples: count('upload_baseline_ms'),
      load_samples: count('upload_load_ms'),
    },
    answered_percent: data.metrics.answered_rate
      ? Number((data.metrics.answered_rate.values.rate * 100).toFixed(1)) : null,
    role: __ENV.ROLE || 'Employee',
    ai_provider: __ENV.AI_PROVIDER || 'not recorded',
    model: __ENV.FLM_CHAT_MODEL || 'not recorded',
    baseline_iterations: BASELINE_ITERATIONS,
    commit: __ENV.GIT_COMMIT || 'not recorded',
    base_url: BASE_URL,
    finished_at: new Date().toISOString(),
  };

  const fmt = (v) => (v === null || v === undefined ? 'n/a' : v.toFixed(0) + ' ms');
  const pct = (v) => (v === null ? 'n/a' : v + '%');
  const text =
    '\nNFR-09 (p90, max degradation ' + MAX_DEGRADATION * 100 + '%)\n' +
    `  questions: baseline ${fmt(askResult.baseline_p90_ms)} -> load ${fmt(askResult.load_p90_ms)} (${pct(askResult.degradation_percent)})\n` +
    `  uploads  : baseline ${fmt(uploadResult.baseline_p90_ms)} -> load ${fmt(uploadResult.load_p90_ms)} (${pct(uploadResult.degradation_percent)})\n` +
    `  samples (ask base/load, upload base/load): ${count('ask_baseline_ms')}/${count('ask_load_ms')}, ${count('upload_baseline_ms')}/${count('upload_load_ms')}\n` +
    `  run valid: ${valid}\n` +
    `  verdict  : ${verdict}\n`;

  return {
    stdout: text,
    'tests/load/results/nfr09_summary.json': JSON.stringify(report, null, 2),
  };
}