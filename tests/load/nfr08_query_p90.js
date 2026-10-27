// NFR-08: p90 of POST /api/ask, answered replies only, under 5 concurrent
// Employees. How to run it: tests/load/README.md.
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import {
  BASE_URL, GIT_SHA, EXPECTED_ROLE, ASK_LIMIT, LOGIN_SPACING_S,
  requireThat, minimumSpacingSeconds, accountEmail, accountRange,
  loginAccounts, sessionForThisVu, warmUp, paceFrom, setupTimeoutSeconds,
  nextQuestion, ask, isValidReply, wasAnswered, validityProblems, throttleCounts,
} from './common.js';

const P90_LIMIT_MS = 4000;
const VUS = Number(__ENV.VUS || 5);
const ITERATIONS = Number(__ENV.ITERATIONS || 100);

// Each VU logs in its own account: VU n is account n, so 01-05 (D-82 rule 1).
const ACCOUNTS = accountRange(1, VUS);

// Every iteration lasts at least this long, start to start (D-82 rule 4). One VU
// is one account and sends one ask per iteration, so this is the spacing of that
// account's asks. 6 s is exactly W/N for 10/min, and a no-answer reply comes back
// fast enough that the floor is what paces the VU: 11 asks then span exactly
// 60 s at the client, and the 11th is a 429 as soon as the 1st was stamped late,
// which Waitress's 4 threads under 5 VUs can do. A floor of at least
// W/(N-1) = 60/9 = 6.67 s holds however late any one ask is stamped
// (common.js, minimumSpacingSeconds): 7 s puts 11 asks more than 9 * 7 = 63 s
// apart at the server. Cost: 100 iterations / 5 VUs * 7 s = 140 s at least.
const ITERATION_FLOOR_S = 7;
requireThat(ITERATION_FLOOR_S >= minimumSpacingSeconds(ASK_LIMIT),
  `ITERATION_FLOOR_S must be at least ${minimumSpacingSeconds(ASK_LIMIT).toFixed(2)} s.`);

// k6's default setupTimeout is 60 s. setup() logs in VUS accounts, 3.5 s apart,
// then makes 2 warm-up asks from account 01 paced at the floor. Typically:
// 4 * 3.5 s + one login + 2 asks of ~7 s = about 30 s. Allowed: every step at its
// worst, 5 * 30 s (login timeout) + 2 * 300 s (ask timeout) + 60 s = 810 s.
const SETUP_TIMEOUT_S = setupTimeoutSeconds(ACCOUNTS.length, ITERATION_FLOOR_S);

// Timed for every ask, and again for answered replies only, because a
// no-answer reply skips generation and comes back much faster.
const allMs = new Trend('ask_all_ms', true);
const answeredMs = new Trend('ask_answered_ms', true);
const answeredRate = new Rate('answered_rate');

// Validity, not latency: these must pass for the run to count.
const VALIDITY_THRESHOLDS = [
  ['http_req_failed{name:ask}', 'rate<0.01'],
  ['checks', 'rate>0.99'],
];

export const options = {
  setupTimeout: `${SETUP_TIMEOUT_S}s`,
  scenarios: {
    query_p90: {
      executor: 'shared-iterations',
      vus: VUS,
      iterations: ITERATIONS,
      maxDuration: '45m',
    },
  },
  // count, so a run with no answered replies reads as NO DATA, not a p90 of 0.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'count'],
  thresholds: {
    ask_answered_ms: [`p(90)<${P90_LIMIT_MS}`],
    'http_req_failed{name:ask}': ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  const sessions = loginAccounts(ACCOUNTS);
  // Account 01 is VU 1's, so its warm-ups are paced like its measured asks.
  warmUp(sessions[0], ITERATION_FLOOR_S);
  return { sessions };
}

export default function (data) {
  const started = Date.now();
  const session = sessionForThisVu(data.sessions);
  const res = ask(session, nextQuestion());
  const valid = check(res, { 'ask returned 200 with documented shape': isValidReply });
  const answered = wasAnswered(res);
  answeredRate.add(answered);
  if (valid) {
    allMs.add(res.timings.duration);
    if (answered) {
      answeredMs.add(res.timings.duration);
    }
  }
  paceFrom(started, ITERATION_FLOOR_S);
}

function ms(value) {
  return value === null || value === undefined ? 'n/a' : value.toFixed(0) + ' ms';
}

export function handleSummary(data) {
  const answeredCount = data.metrics.ask_answered_ms
    ? data.metrics.ask_answered_ms.values.count : 0;
  const allCount = data.metrics.ask_all_ms ? data.metrics.ask_all_ms.values.count : 0;
  // A Trend with a threshold is reported even with no samples, with a p90 of 0.
  const answeredP90 = answeredCount > 0 ? data.metrics.ask_answered_ms.values['p(90)'] : null;
  const allP90 = allCount > 0 ? data.metrics.ask_all_ms.values['p(90)'] : null;
  const answeredPct = data.metrics.answered_rate
    ? Number((data.metrics.answered_rate.values.rate * 100).toFixed(1)) : null;

  const problems = validityProblems(data, VALIDITY_THRESHOLDS);
  const valid = problems.length === 0;
  // INVALID first: a 429 makes the run invalid whatever else it measured (D-82 rule 5).
  const verdict =
    !valid ? 'INVALID RUN'
    : answeredP90 === null ? 'NO DATA'
    : answeredP90 < P90_LIMIT_MS ? 'PASS'
    : 'FAIL';

  const report = {
    requirement: 'NFR-08',
    verdict,
    run_valid: valid,
    invalid_reasons: problems,
    throttled_429: throttleCounts(data),
    p90_answered_ms: answeredP90,
    p90_all_replies_ms: allP90,
    limit_ms: P90_LIMIT_MS,
    answered_samples: answeredCount,
    all_reply_samples: allCount,
    answered_percent: answeredPct,
    commit_sha: GIT_SHA || null,
    role: EXPECTED_ROLE,
    role_checked_at_login: true,
    accounts: `${accountEmail(ACCOUNTS[0])} to ${accountEmail(ACCOUNTS[ACCOUNTS.length - 1])}, one per VU`,
    ai_provider: __ENV.AI_PROVIDER || 'not recorded',
    model: __ENV.FLM_CHAT_MODEL || 'not recorded',
    vus: VUS,
    iterations: ITERATIONS,
    iteration_floor_s: ITERATION_FLOOR_S,
    login_spacing_s: LOGIN_SPACING_S,
    base_url: BASE_URL,
    finished_at: new Date().toISOString(),
  };

  const text =
    '\nNFR-08 (p90, answered replies only)\n' +
    `  p90 answered   : ${ms(answeredP90)} (limit ${P90_LIMIT_MS} ms, ${answeredCount} samples)\n` +
    `  p90 all replies: ${ms(allP90)}\n` +
    `  answered       : ${answeredPct === null ? 'n/a' : answeredPct + '%'}\n` +
    `  VUs / iterations: ${VUS} / ${ITERATIONS}\n` +
    `  commit         : ${GIT_SHA || 'not recorded'}\n` +
    `  run valid      : ${valid}\n` +
    problems.map((p) => `    INVALID: ${p}\n`).join('') +
    `  verdict        : ${verdict}\n`;

  return {
    stdout: text,
    'tests/load/results/nfr08_summary.json': JSON.stringify(report, null, 2),
  };
}
