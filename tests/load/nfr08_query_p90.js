// NFR-08: p90 of POST /api/ask, answered replies only, under 5 concurrent
// Employees. Objective 03's p90 is measured at 5 (D-84 decision 3). How to run
// it: tests/load/README.md, through run.ps1.
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import {
  BASE_URL, EXPECTED_ROLE, ASK_LIMIT, ASK_TIMEOUT_S, LOGIN_SPACING_S,
  requireThat, minimumSpacingSeconds, accountEmail, accountRange,
  loginAccounts, sessionForThisVu, warmUp, paceFrom, setupTimeoutSeconds,
  nextQuestion, ask, isValidReply, wasAnswered, validityProblems, throttleCounts,
  runRecord, runRecordLines, observedServer,
} from './common.js';

const P90_LIMIT_MS = 4000;
// D-84 decision 3 fixes 5 for Objective 03. VUS is still read so the script can be
// tried smaller, and the JSON records whatever ran: the single-user end-to-end
// baseline of 1 November 2026 is VUS=1, ITERATIONS=20.
const VUS = Number(__ENV.VUS || 5);
// 25 since 1 November 2026, down from 100, so the rerun fits the gate day: the
// first run's answered asks had a p90 of 251 s at 5 users, so 25 asks are about 5
// rounds of that. Recorded in corpus/objective-02/runs/2026-11-01/nfr08-runs.md.
const ITERATIONS = Number(__ENV.ITERATIONS || 25);

// Reported beside the measured p90, as D-84 decision 3 asks; this run does not
// measure it. It is not the same measure as ask_answered_ms: it times one
// generation call in-process (GenerationAttempt.seconds in apps/ai/generation.py),
// so it leaves out the question's embedding, retrieval and HTTP. Even one user
// over HTTP would read above it.
const SINGLE_USER_BASELINE = {
  p90_ms: 8900,
  measures: 'one generation call (FLM chat completion and schema parse), timed in-process; ' +
            "excludes the question's embedding, retrieval and HTTP",
  conditions: 'one user, sequential, 50 calls, six-chunk corpus, with the history block',
  source: 'docs/flm-baseline.md, Stage 4 item 9a',
  measured_by_this_run: false,
};

// Each VU logs in its own account: VU n is account n, so 01-05 (D-82 rule 1).
const ACCOUNTS = accountRange(1, VUS);

// Every iteration lasts at least this long, start to start (D-82 rule 4). One VU
// is one account and sends one ask per iteration, so this is the spacing of that
// account's asks. 6 s is exactly W/N for 10/min, and a no-answer reply comes back
// fast enough that the floor is what paces the VU: 11 asks then span exactly
// 60 s at the client, and the 11th is a 429 as soon as the 1st was stamped later
// than the 11th. Under D-85's 24 threads, 5 VUs never wait for a thread, so the
// difference should be milliseconds rather than a queue (unmeasured), but any
// difference is enough.
// A floor of at least W/(N-1) = 60/9 = 6.67 s holds however late any one ask is
// stamped, at any thread count (common.js, minimumSpacingSeconds): 7 s puts 11
// asks more than 9 * 7 = 63 s apart at the server. Cost: 25 iterations / 5 VUs
// * 7 s = 35 s at least.
const ITERATION_FLOOR_S = 7;
requireThat(ITERATION_FLOOR_S >= minimumSpacingSeconds(ASK_LIMIT),
  `ITERATION_FLOOR_S must be at least ${minimumSpacingSeconds(ASK_LIMIT).toFixed(2)} s.`);

// k6's default setupTimeout is 60 s. setup() logs in VUS accounts, 3.5 s apart,
// then makes 2 warm-up asks from account 01 paced at the floor. Typically:
// 4 * 3.5 s + one login + 2 asks of ~7 s = about 30 s. Allowed: every step at its
// worst, 5 * 30 s (login timeout) + 2 * 2,835 s (ask timeout) + 60 s = 5,880 s.
const SETUP_TIMEOUT_S = setupTimeoutSeconds(ACCOUNTS.length, ITERATION_FLOOR_S);

// k6 ends the scenario at maxDuration and interrupts any ask still in flight,
// which abandons it as a timeout does. So maxDuration follows ASK_TIMEOUT_S
// rather than being a guess (it was 45 m, shorter than one ask's timeout now).
// No iteration lasts longer than ASK_TIMEOUT_S + ITERATION_FLOOR_S, and a VU
// starts its next iteration as soon as one ends, so each VU has started its
// (k+1)th by k such lengths. Every one of ITERATIONS has therefore started by
// ceil(ITERATIONS / VUS) - 1 lengths and finished by ceil(ITERATIONS / VUS).
// It is a ceiling only: at 5 VUs and 25 iterations it is 5 * 2,842 s = 3 h 57 m,
// and a run whose asks come back takes minutes.
const MAX_DURATION_S = Math.ceil(ITERATIONS / VUS) * (ASK_TIMEOUT_S + ITERATION_FLOOR_S);

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
      maxDuration: `${MAX_DURATION_S}s`,
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
  // Before the warm-ups, so a wrong server is reported before they take minutes.
  // It reaches handleSummary() as data.setup_data (D-85 decision 4).
  const observed = observedServer(sessions);
  // Account 01 is VU 1's, so its warm-ups are paced like its measured asks.
  warmUp(sessions[0], ITERATION_FLOOR_S);
  return { sessions, observed_server: observed };
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
  // Every measured ask adds to answered_rate, a failed one as not answered, so its
  // denominator is all measured asks, not only the replies in ask_all_ms.
  const rate = data.metrics.answered_rate ? data.metrics.answered_rate.values : null;
  const answeredPct = rate ? Number((rate.rate * 100).toFixed(1)) : null;
  const asksMeasured = !rate ? 0
    : Number.isFinite(rate.passes) && Number.isFinite(rate.fails) ? rate.passes + rate.fails
    : null;

  const problems = validityProblems(data, VALIDITY_THRESHOLDS);
  const valid = problems.length === 0;
  // INVALID first: a 429 makes the run invalid whatever else it measured (D-82 rule 5).
  const verdict =
    !valid ? 'INVALID RUN'
    : answeredP90 === null ? 'NO DATA'
    : answeredP90 < P90_LIMIT_MS ? 'PASS'
    : 'FAIL';

  // In D-84 decision 3's order: the answered-only p90 against 4 s, then the
  // all-replies p90, the answered rate and the baseline beside it, then what was
  // measured.
  const report = {
    requirement: 'NFR-08',
    verdict,
    run_valid: valid,
    invalid_reasons: problems,
    p90_answered_ms: answeredP90,
    limit_ms: P90_LIMIT_MS,
    answered_samples: answeredCount,
    p90_all_replies_ms: allP90,
    all_reply_samples: allCount,
    answered_percent: answeredPct,
    asks_measured: asksMeasured,
    single_user_baseline: SINGLE_USER_BASELINE,
    ...runRecord(data),
    throttled_429: throttleCounts(data),
    role: EXPECTED_ROLE,
    role_checked_at_login: true,
    accounts: `${accountEmail(ACCOUNTS[0])} to ${accountEmail(ACCOUNTS[ACCOUNTS.length - 1])}, one per VU`,
    ai_provider: __ENV.AI_PROVIDER || 'not recorded',
    model: __ENV.FLM_CHAT_MODEL || 'not recorded',
    vus: VUS,
    iterations: ITERATIONS,
    iteration_floor_s: ITERATION_FLOOR_S,
    ask_timeout_s: ASK_TIMEOUT_S,
    max_duration_s: MAX_DURATION_S,
    login_spacing_s: LOGIN_SPACING_S,
    base_url: BASE_URL,
    finished_at: new Date().toISOString(),
  };

  const label = (name) => `  ${name.padEnd(21)}: `;
  const text =
    `\nNFR-08: p90 of POST /api/ask at ${VUS} concurrent users\n` +
    `${label('p90, answered only')}${ms(answeredP90)} against ${P90_LIMIT_MS} ms (${answeredCount} samples)\n` +
    `${label('p90, all replies')}${ms(allP90)} (${allCount} samples)\n` +
    `${label('answered rate')}${answeredPct === null ? 'n/a' : answeredPct + '%'} (${answeredCount} of ${asksMeasured === null ? 'n/a' : asksMeasured} asks)\n` +
    `${label('single-user baseline')}${ms(SINGLE_USER_BASELINE.p90_ms)}, not measured by this run: ` +
    'p90 of one generation call, in-process, without embedding, retrieval or HTTP ' +
    `(${SINGLE_USER_BASELINE.source})\n` +
    runRecordLines(label, data) +
    `${label('VUs / iterations')}${VUS} / ${ITERATIONS}\n` +
    `${label('ask timeout / max')}${ASK_TIMEOUT_S} s / ${MAX_DURATION_S} s\n` +
    `${label('run valid')}${valid}\n` +
    problems.map((p) => `    INVALID: ${p}\n`).join('') +
    `${label('verdict')}${verdict}\n`;

  return {
    stdout: text,
    'tests/load/results/nfr08_summary.json': JSON.stringify(report, null, 2),
  };
}
