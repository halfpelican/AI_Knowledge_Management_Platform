import { sleep, check } from 'k6';
import { Rate } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';
import { BASE_URL, loginOnce, ask, isValidReply, wasAnswered } from './common.js';

const answeredRate = new Rate('answered_rate');
const P90_LIMIT_MS = 4000;

export const options = {
  scenarios: {
    query_p90: {
      executor: 'shared-iterations',
      vus: Number(__ENV.VUS || 1),
      iterations: Number(__ENV.ITERATIONS || 100),
      maxDuration: '25m',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)'],
  thresholds: {
    'http_req_duration{name:ask}': [`p(90)<${P90_LIMIT_MS}`],
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

export default function (cookies) {
  const res = ask(cookies);
  check(res, { 'ask returned 200 with documented shape': isValidReply });
  answeredRate.add(wasAnswered(res));
  sleep(1);
}

export function handleSummary(data) {
  const m = data.metrics['http_req_duration{name:ask}'];
  const p90 = m ? m.values['p(90)'] : null;
  const answered = data.metrics['answered_rate'];
  const answeredPct = answered ? (answered.values.rate * 100).toFixed(1) : 'n/a';

  const verdict = p90 === null ? 'NO DATA' : p90 < P90_LIMIT_MS ? 'PASS' : 'FAIL';

  const report = {
    requirement: 'NFR-08',
    base_url: BASE_URL,
    p90_ms: p90,
    limit_ms: P90_LIMIT_MS,
    verdict,
    answered_percent: answeredPct,
    finished_at: new Date().toISOString(),
  };

  const line = `\nNFR-08: p90 = ${p90 === null ? 'n/a' : p90.toFixed(0) + ' ms'} (limit ${P90_LIMIT_MS} ms) -> ${verdict}\nAnswered (not no-answer) replies: ${answeredPct}%\n`;

  return {
    stdout: textSummary(data, { indent: ' ', enableColors: false }) + line,
    'tests/load/results/nfr08_summary.json': JSON.stringify(report, null, 2),
  };
}