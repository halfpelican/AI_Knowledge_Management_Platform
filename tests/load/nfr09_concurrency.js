import { sleep, check } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';
import { BASE_URL, loginOnce, ask, isValidReply, wasAnswered } from './common.js';

const baselineMs = new Trend('ask_baseline_ms', true);
const loadMs = new Trend('ask_load_ms', true);
const answeredRate = new Rate('answered_rate');

const MAX_DEGRADATION = 0.25;
const CONCURRENT_USERS = 20;

export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-vus',
      exec: 'baseline',
      vus: 1,
      duration: '3m',
      startTime: '0s',
      gracefulStop: '60s',
    },
    load: {
      executor: 'constant-vus',
      exec: 'load',
      vus: CONCURRENT_USERS,
      duration: '3m',
      startTime: '3m30s',
      gracefulStop: '60s',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)'],
  thresholds: {
    'http_req_failed{name:ask}': ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  const cookies = loginOnce();
  ask(cookies);
  ask(cookies);
  return cookies;
}

function oneQuestion(cookies, trend) {
  const res = ask(cookies);
  const ok = check(res, { 'ask returned 200 with documented shape': isValidReply });
  if (ok) {
    trend.add(res.timings.duration);
  }
  answeredRate.add(wasAnswered(res));
  sleep(1);
}

export function baseline(cookies) {
  oneQuestion(cookies, baselineMs);
}

export function load(cookies) {
  oneQuestion(cookies, loadMs);
}

export function handleSummary(data) {
  const b = data.metrics['ask_baseline_ms'];
  const l = data.metrics['ask_load_ms'];
  const baselineP90 = b ? b.values['p(90)'] : null;
  const loadP90 = l ? l.values['p(90)'] : null;
  const answered = data.metrics['answered_rate'];
  const answeredPct = answered ? (answered.values.rate * 100).toFixed(1) : 'n/a';

  let ratio = null;
  let verdict = 'NO DATA';
  if (baselineP90 && loadP90) {
    ratio = loadP90 / baselineP90;
    verdict = ratio <= 1 + MAX_DEGRADATION ? 'PASS' : 'FAIL';
  }

  const report = {
    requirement: 'NFR-09',
    base_url: BASE_URL,
    concurrent_users: CONCURRENT_USERS,
    baseline_p90_ms: baselineP90,
    load_p90_ms: loadP90,
    degradation_percent: ratio === null ? null : Number(((ratio - 1) * 100).toFixed(1)),
    max_allowed_degradation_percent: MAX_DEGRADATION * 100,
    verdict,
    answered_percent: answeredPct,
    finished_at: new Date().toISOString(),
  };

  const line =
    '\nNFR-09 (p90):\n' +
    `  baseline (1 user)   : ${baselineP90 === null ? 'n/a' : baselineP90.toFixed(0) + ' ms'}\n` +
    `  load (${CONCURRENT_USERS} users)     : ${loadP90 === null ? 'n/a' : loadP90.toFixed(0) + ' ms'}\n` +
    `  degradation         : ${ratio === null ? 'n/a' : ((ratio - 1) * 100).toFixed(1) + '%'} (max ${MAX_DEGRADATION * 100}%)\n` +
    `  verdict             : ${verdict}\n` +
    `  answered replies    : ${answeredPct}%\n`;

  return {
    stdout: textSummary(data, { indent: ' ', enableColors: false }) + line,
    'tests/load/results/nfr09_summary.json': JSON.stringify(report, null, 2),
  };
}