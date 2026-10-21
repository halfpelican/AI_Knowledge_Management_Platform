import { sleep, check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import {
  BASE_URL, QUESTIONS, loginOnce, nextQuestion, ask,
  isValidReply, wasAnswered, runWasValid,
} from './common.js';

const P90_LIMIT_MS = 4000;
const VUS = Number(__ENV.VUS || 5);
const ITERATIONS = Number(__ENV.ITERATIONS || 100);

// Timed for every ask, and again for answered replies only, because a
// no-answer reply skips generation and comes back much faster.
const allMs = new Trend('ask_all_ms', true);
const answeredMs = new Trend('ask_answered_ms', true);
const answeredRate = new Rate('answered_rate');

export const options = {
  scenarios: {
    query_p90: {
      executor: 'shared-iterations',
      vus: VUS,
      iterations: ITERATIONS,
      maxDuration: '45m',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)'],
  thresholds: {
    ask_answered_ms: [`p(90)<${P90_LIMIT_MS}`],
    'http_req_failed{name:ask}': ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  const cookies = loginOnce();
  // Untimed warm-up (tagged 'warmup', so it is not counted as a measured ask).
  ask(cookies, QUESTIONS[0], 'warmup');
  ask(cookies, QUESTIONS[0], 'warmup');
  return cookies;
}

export default function (cookies) {
  const res = ask(cookies, nextQuestion());
  const valid = check(res, { 'ask returned 200 with documented shape': isValidReply });
  const answered = wasAnswered(res);
  answeredRate.add(answered);
  if (valid) {
    allMs.add(res.timings.duration);
    if (answered) {
      answeredMs.add(res.timings.duration);
    }
  }
  sleep(1);
}

function ms(value) {
  return value === null || value === undefined ? 'n/a' : value.toFixed(0) + ' ms';
}

export function handleSummary(data) {
  const answeredP90 = data.metrics.ask_answered_ms
    ? data.metrics.ask_answered_ms.values['p(90)'] : null;
  const allP90 = data.metrics.ask_all_ms
    ? data.metrics.ask_all_ms.values['p(90)'] : null;
  const answeredCount = data.metrics.ask_answered_ms
    ? data.metrics.ask_answered_ms.values.count : 0;
  const answeredPct = data.metrics.answered_rate
    ? Number((data.metrics.answered_rate.values.rate * 100).toFixed(1)) : null;

  const valid = runWasValid(data);
  const verdict =
    answeredP90 === null ? 'NO DATA'
    : !valid ? 'INVALID RUN'
    : answeredP90 < P90_LIMIT_MS ? 'PASS'
    : 'FAIL';

  const report = {
    requirement: 'NFR-08',
    verdict,
    p90_answered_ms: answeredP90,
    p90_all_replies_ms: allP90,
    limit_ms: P90_LIMIT_MS,
    answered_samples: answeredCount,
    answered_percent: answeredPct,
    run_valid: valid,
    role: __ENV.ROLE || 'Employee',
    ai_provider: __ENV.AI_PROVIDER || 'not recorded',
    model: __ENV.FLM_CHAT_MODEL || 'not recorded',
    vus: VUS,
    iterations: ITERATIONS,
    commit: __ENV.GIT_COMMIT || 'not recorded',
    base_url: BASE_URL,
    finished_at: new Date().toISOString(),
  };

  const text =
    '\nNFR-08 (p90, answered replies only)\n' +
    `  p90 answered   : ${ms(answeredP90)} (limit ${P90_LIMIT_MS} ms, ${answeredCount} samples)\n` +
    `  p90 all replies: ${ms(allP90)}\n` +
    `  answered       : ${answeredPct === null ? 'n/a' : answeredPct + '%'}\n` +
    `  run valid      : ${valid}\n` +
    `  VUs / iterations: ${VUS} / ${ITERATIONS}\n` +
    `  verdict        : ${verdict}\n`;

  return {
    stdout: text,
    'tests/load/results/nfr08_summary.json': JSON.stringify(report, null, 2),
  };
}