// NFR-09: p90 of asks and uploads under 20 concurrent Employees, against a
// one-user baseline, at most 25% worse. How to run it: tests/load/README.md.
import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import {
  BASE_URL, GIT_SHA, EXPECTED_ROLE, ASK_LIMIT, INGESTION_LIMIT, LOGIN_SPACING_S,
  requireThat, minimumSpacingSeconds, accountEmail, accountRange,
  loginAccounts, sessionForThisVu, warmUp, paceFrom, setupTimeoutSeconds,
  nextQuestion, ask, isValidReply, wasAnswered, validityProblems, throttleCounts,
  recordResponse,
} from './common.js';

const MAX_DEGRADATION = 0.25;
const CONCURRENT_USERS = 20;
const BASELINE_ITERATIONS = Number(__ENV.BASELINE_ITERATIONS || 50);

// Accounts (D-82 rules 1 and 3): load-phase VU n is account n, 01-20. The
// baseline has its own, 21, so its uploads never share an hour's ingestion
// budget with a load-phase user. The baseline takes it by scenario, not by VU
// number: the phases never overlap, so k6 runs at most 20 VUs and lends one of
// them to the baseline first.
const LOAD_ACCOUNTS = accountRange(1, CONCURRENT_USERS);
const BASELINE_ACCOUNT = CONCURRENT_USERS + 1;

const BASELINE_MAX_DURATION_S = 15 * 60;
const LOAD_DURATION_S = 10 * 60;

// Every round (one ask, then one upload) lasts at least this long, start to
// start, in both phases, so the phases differ only in how many users run them.
// One VU is one account, so this spaces that account's asks and its uploads.
//
// Uploads (D-79, 60/hour per account, rejected uploads included): a load-phase
// account uploads once per round for 600 s. A 6 s floor would allow 100. 10 s
// allows 60, the limit itself: no upload to spare, and the 61st round falls due
// at the phase's 600 s mark, kept out only by k6 not starting an iteration once
// the duration is up. Counting both ends of the phase, a floor f starts at most
// floor(600 / f) + 1 rounds: 10.5 s gives 58, two under the limit, with the 59th
// due 9 s after the phase ends. The baseline account makes BASELINE_ITERATIONS
// uploads, 50 by default, all inside one hour: 50 <= 60.
// Asks (D-79, 10/min): at least 60/9 = 6.67 s (common.js,
// minimumSpacingSeconds); 10.5 s is 9 * 10.5 = 94.5 s for 11 asks.
// Cost: the baseline takes at least 50 * 10.5 s = 525 s of its 900 s.
const ROUND_FLOOR_S = 10.5;

const maxLoadRounds = Math.floor(LOAD_DURATION_S / ROUND_FLOOR_S) + 1;
requireThat(ROUND_FLOOR_S >= minimumSpacingSeconds(ASK_LIMIT),
  `ROUND_FLOOR_S must be at least ${minimumSpacingSeconds(ASK_LIMIT).toFixed(2)} s for the ask rate.`);
requireThat(maxLoadRounds <= INGESTION_LIMIT.requests,
  `A ${ROUND_FLOOR_S} s floor allows ${maxLoadRounds} uploads per account in the load phase; ` +
  `the ingestion limit is ${INGESTION_LIMIT.requests} an hour.`);
requireThat(BASELINE_ITERATIONS <= INGESTION_LIMIT.requests,
  `BASELINE_ITERATIONS (${BASELINE_ITERATIONS}) uploads from one account would pass the ` +
  `ingestion limit of ${INGESTION_LIMIT.requests} an hour.`);
requireThat(BASELINE_ITERATIONS * ROUND_FLOOR_S <= BASELINE_MAX_DURATION_S,
  `${BASELINE_ITERATIONS} baseline rounds of at least ${ROUND_FLOOR_S} s cannot finish ` +
  `inside the baseline's ${BASELINE_MAX_DURATION_S} s.`);

// k6's default setupTimeout is 60 s, and 21 logins 3.5 s apart take 70 s alone.
// setup() then makes 2 warm-up asks from account 01, paced at the floor.
// Typically: 20 * 3.5 s + one login + 2 * 10.5 s = about 92 s. Allowed: every
// step at its worst, 21 * 30 s (login timeout) + 2 * 300 s (ask timeout) + 60 s
// = 1290 s. Sessions expire after 60 idle minutes (SESSION_INACTIVITY_MINUTES);
// a load-phase account is idle from its login to the load phase, at most
// 1290 s + 20 m = 41.5 m.
const SETUP_TIMEOUT_S = setupTimeoutSeconds(LOAD_ACCOUNTS.length + 1, ROUND_FLOOR_S);

const askBaselineMs = new Trend('ask_baseline_ms', true);
const askLoadMs = new Trend('ask_load_ms', true);
const uploadBaselineMs = new Trend('upload_baseline_ms', true);
const uploadLoadMs = new Trend('upload_load_ms', true);
const answeredRate = new Rate('answered_rate');

// Validity, not latency: these must pass for the run to count.
const VALIDITY_THRESHOLDS = [
  ['http_req_failed{name:ask}', 'rate<0.01'],
  ['http_req_failed{name:upload}', 'rate<0.01'],
  ['checks', 'rate>0.99'],
];

export const options = {
  setupTimeout: `${SETUP_TIMEOUT_S}s`,
  scenarios: {
    // Phase 1: one user, a fixed number of rounds (stable, repeatable baseline).
    baseline: {
      executor: 'per-vu-iterations',
      exec: 'baseline',
      vus: 1,
      iterations: BASELINE_ITERATIONS,
      maxDuration: `${BASELINE_MAX_DURATION_S}s`,
      startTime: '0s',
      gracefulStop: '5m',
    },
    // Phase 2: 20 users. Starts after the baseline's maxDuration (15m) plus
    // its gracefulStop (5m), so the two phases can never overlap.
    load: {
      executor: 'constant-vus',
      exec: 'load',
      vus: CONCURRENT_USERS,
      duration: `${LOAD_DURATION_S}s`,
      startTime: '20m',
      gracefulStop: '5m',
    },
  },
  // count, so a phase with no samples reads as NO DATA, not a p90 of 0.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'count'],
  thresholds: {
    'http_req_failed{name:ask}': ['rate<0.01'],
    'http_req_failed{name:upload}': ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  const sessions = loginAccounts([...LOAD_ACCOUNTS, BASELINE_ACCOUNT]);
  // Account 01's next ask is in the load phase, at least 20 minutes later.
  warmUp(sessions[0], ROUND_FLOOR_S);
  return {
    load: sessions.slice(0, CONCURRENT_USERS),
    baseline: sessions[CONCURRENT_USERS],
  };
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
function uploadDocument(session) {
  const unique = `${exec.vu.idInTest}_${exec.scenario.iterationInTest}_${Date.now()}`;
  const body = PARAGRAPH.repeat(3) + `\nUnique reference: ${unique}\n`;
  const res = http.post(
    `${BASE_URL}/api/documents`,
    {
      file: http.file(body, `loadtest_${unique}.txt`, 'text/plain'),
      title: `Load test ${unique}`,
      department: 'LoadTest',
    },
    {
      // No Content-Type header: k6 sets the multipart boundary itself.
      headers: { 'X-CSRFToken': session.cookies.csrftoken },
      cookies: session.cookies,
      tags: { name: 'upload' },
      timeout: '300s',
    }
  );
  recordResponse(res, 'upload', session.account);
  return res;
}

function oneRound(session, askTrend, uploadTrend) {
  const started = Date.now();
  const askRes = ask(session, nextQuestion());
  const askOk = check(askRes, { 'ask returned 200 with documented shape': isValidReply });
  const answered = wasAnswered(askRes);
  answeredRate.add(answered);
  // Answered replies only: a no-answer reply skips generation and is faster.
  if (askOk && answered) {
    askTrend.add(askRes.timings.duration);
  }

  const upRes = uploadDocument(session);
  const upOk = check(upRes, { 'upload returned 201': (r) => r.status === 201 });
  if (upOk) {
    uploadTrend.add(upRes.timings.duration);
  }
  paceFrom(started, ROUND_FLOOR_S);
}

export function baseline(data) {
  oneRound(data.baseline, askBaselineMs, uploadBaselineMs);
}

export function load(data) {
  oneRound(sessionForThisVu(data.load), askLoadMs, uploadLoadMs);
}

export function handleSummary(data) {
  const count = (name) => (data.metrics[name] ? data.metrics[name].values.count : 0);
  // A Trend with no samples has no p90 worth reading.
  const p90 = (name) => (count(name) > 0 ? data.metrics[name].values['p(90)'] : null);

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

  const problems = validityProblems(data, VALIDITY_THRESHOLDS);
  const valid = problems.length === 0;
  const haveData = askResult.baseline_p90_ms && askResult.load_p90_ms &&
                   uploadResult.baseline_p90_ms && uploadResult.load_p90_ms;

  // INVALID first: a 429 makes the run invalid whatever else it measured (D-82 rule 5).
  const verdict = !valid ? 'INVALID RUN'
    : !haveData ? 'NO DATA'
    : askResult.pass && uploadResult.pass ? 'PASS'
    : 'FAIL';

  const report = {
    requirement: 'NFR-09',
    verdict,
    run_valid: valid,
    invalid_reasons: problems,
    throttled_429: throttleCounts(data),
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
    commit_sha: GIT_SHA || null,
    role: EXPECTED_ROLE,
    role_checked_at_login: true,
    accounts: {
      load: `${accountEmail(LOAD_ACCOUNTS[0])} to ${accountEmail(LOAD_ACCOUNTS[LOAD_ACCOUNTS.length - 1])}, one per VU`,
      baseline: accountEmail(BASELINE_ACCOUNT),
    },
    ai_provider: __ENV.AI_PROVIDER || 'not recorded',
    model: __ENV.FLM_CHAT_MODEL || 'not recorded',
    baseline_iterations: BASELINE_ITERATIONS,
    round_floor_s: ROUND_FLOOR_S,
    login_spacing_s: LOGIN_SPACING_S,
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
    `  commit   : ${GIT_SHA || 'not recorded'}\n` +
    `  run valid: ${valid}\n` +
    problems.map((p) => `    INVALID: ${p}\n`).join('') +
    `  verdict  : ${verdict}\n`;

  return {
    stdout: text,
    'tests/load/results/nfr09_summary.json': JSON.stringify(report, null, 2),
  };
}
