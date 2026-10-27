// Shared helpers for the NFR-08 and NFR-09 load tests. How to run them, and why
// the pacing numbers below are what they are: tests/load/README.md (D-82).
import http from 'k6/http';
import exec from 'k6/execution';
import { check, fail, sleep } from 'k6';
import { Counter } from 'k6/metrics';

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TEST_PASSWORD = __ENV.TEST_PASSWORD;

// One Employee account per virtual user (D-82 rule 1), created by
//   manage.py create_load_test_users --count 21
// as loadtest01@example.com ... loadtest21@example.com, every one with the
// password in LOAD_TEST_PASSWORD. TEST_PASSWORD must be that same value.
export const TEST_EMAIL_PREFIX = __ENV.TEST_EMAIL_PREFIX || 'loadtest';
export const TEST_EMAIL_DOMAIN = __ENV.TEST_EMAIL_DOMAIN || 'example.com';
export const EXPECTED_ROLE = 'Employee';

// The commit the run measured, recorded in the results JSON (D-82 rule 7). k6
// cannot run git, so it is passed in. A run without it is refused before it
// starts, rather than recorded as "unknown" after 35 minutes.
export const GIT_SHA = __ENV.GIT_SHA || '';
const SHA_PATTERN = /^[0-9a-f]{7,40}$/i;

// Init-time refusals: thrown here, they stop k6 before setup() sends anything.
export function requireThat(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

requireThat(!__ENV.TEST_EMAIL,
  'TEST_EMAIL is no longer read: each VU logs in its own numbered account ' +
  `(${TEST_EMAIL_PREFIX}01@${TEST_EMAIL_DOMAIN} ...). Drop -e TEST_EMAIL; see tests/load/README.md.`);
requireThat(!__ENV.GIT_COMMIT || __ENV.GIT_SHA,
  'GIT_COMMIT was renamed GIT_SHA. Pass -e GIT_SHA=<output of git rev-parse HEAD>.');
requireThat(TEST_PASSWORD,
  'Set -e TEST_PASSWORD to the LOAD_TEST_PASSWORD the accounts were created with.');
requireThat(SHA_PATTERN.test(GIT_SHA),
  `Set -e GIT_SHA to the commit under test (git rev-parse HEAD); got "${GIT_SHA}".`);

// --- The server's limits, copied from apps/core/constants.py ------------------
// k6 cannot import Python, so these are copies. If a rate there changes, change
// it here: the pacing assertions in each script are computed from these.
export const AUTH_LIMIT = { requests: 20, windowSeconds: 60 };        // D-26, per address
export const ASK_LIMIT = { requests: 10, windowSeconds: 60 };         // D-79, per user
export const INGESTION_LIMIT = { requests: 60, windowSeconds: 3600 }; // D-79, per user

// The spacing that keeps one sequential client under a sliding-window limit of
// N requests per W seconds, however late the server stamps any one request.
//
// DRF stamps a request when its throttle runs, which can be well after k6 sent
// it: Waitress has 4 threads by default, so with more VUs than threads a request
// can wait in its queue first. Spacing the *sends* W/N apart is therefore not
// enough: if request k waited and request k+N did not, the server sees them less
// than W apart and the (N+1)th is a 429. What does hold, because a VU sends
// nothing until its previous reply is back, is
//   stamp(k+N) >= send(k+N) >= send(k+1) + (N-1)*spacing > stamp(k) + (N-1)*spacing,
// so a spacing of at least W/(N-1) keeps every N+1 consecutive requests more
// than W apart at the server. That is 60/9 = 6.67 s for asks and
// 60/19 = 3.16 s for logins. (The bound needs the VU to have had its reply: an
// ask that k6 abandons at its timeout is not covered; see ASK_TIMEOUT_S.)
export function minimumSpacingSeconds(limit) {
  return limit.windowSeconds / (limit.requests - 1);
}

// Logins at least this far apart, start to start (D-82 rule 2). 3 s is exactly
// W/N for 20/min: 21 logins 3 s apart span exactly 60 s, and the 21st is a 429
// the moment any earlier one is stamped late. 3.5 s spans 19 * 3.5 = 66.5 s.
export const LOGIN_SPACING_S = 3.5;
export const LOGIN_TIMEOUT_S = 30;
requireThat(LOGIN_SPACING_S >= minimumSpacingSeconds(AUTH_LIMIT),
  `LOGIN_SPACING_S must be at least ${minimumSpacingSeconds(AUTH_LIMIT).toFixed(2)} s.`);

// Long on purpose: the single NPU queues requests, so a slow system should show
// up as a measured FAIL, not a timeout. It is shorter than the server's own worst
// case (D-79: 300 s per generation attempt, 3 attempts, plus the question's
// embedding), so an ask k6 abandons can still be holding that account's
// in-flight slot, and the account's next ask is then a 429 with code
// ask_in_flight. The validity gate names that kind apart.
export const ASK_TIMEOUT_S = 300;

// Two untimed asks before measuring, so the first measured ask does not pay for
// loading the model.
export const WARMUP_ASKS = 2;

// Run as an Employee. Every question below is answerable by an Employee.
export const QUESTIONS = [
  'What is the leave policy for annual leave?',
  'What are the rules for acceptable use of IT equipment?',
  'What does the health and safety induction cover?',
  'How are records managed and retained?',
  'What are the procurement guidelines for purchasing?',
  'How do I make a complaint?',
  'What does the remote work agreement say?',
  'How do I submit an expense claim?',
  'What does the data privacy notice say about personal information?',
  'What was discussed in the weekly operations standup?',
];

// --- 429 accounting (D-82 rule 5) ------------------------------------------------
// Every response passes through recordResponse(), which adds 0 or 1, so the
// counter exists whenever any response was seen. Its absence therefore means
// nothing was recorded, and the gate treats that as invalid rather than as zero.
const http429 = new Counter('http_429');
const http429InFlight = new Counter('http_429_ask_in_flight');

export function recordResponse(res, name, account) {
  const throttled = res.status === 429;
  http429.add(throttled ? 1 : 0);
  if (!throttled) return;
  let code = '';
  try {
    code = res.json('code') || '';
  } catch (e) {
    code = '';
  }
  if (code === 'ask_in_flight') {
    http429InFlight.add(1);
  }
  console.warn(
    `429 on ${name} for ${accountEmail(account)}` +
    (code ? ` (code ${code})` : ` (rate limit, Retry-After ${res.headers['Retry-After'] || 'none'})`) +
    ': this run is INVALID (D-82 rule 5).'
  );
}

// --- Accounts and sessions ---------------------------------------------------------

export function accountEmail(number) {
  return `${TEST_EMAIL_PREFIX}${String(number).padStart(2, '0')}@${TEST_EMAIL_DOMAIN}`;
}

export function accountRange(first, last) {
  const numbers = [];
  for (let n = first; n <= last; n++) numbers.push(n);
  return numbers;
}

// Sleeps out whatever is left of `seconds` since `startedMs`. The extra
// millisecond covers Date.now() truncating, so the gap is never short.
export function paceFrom(startedMs, seconds) {
  const remaining = seconds - (Date.now() - startedMs) / 1000 + 0.001;
  if (remaining > 0) sleep(remaining);
}

function loginAccount(number) {
  const email = accountEmail(number);
  const res = http.post(
    `${BASE_URL}/api/auth/login`,
    JSON.stringify({ email, password: TEST_PASSWORD }),
    {
      headers: { 'Content-Type': 'application/json' },
      // A fresh jar for every login. setup() is one VU with one jar, which would
      // otherwise send the previous account's session cookie with this login:
      // DRF would authenticate the POST as that account and refuse it for CSRF.
      jar: new http.CookieJar(),
      tags: { name: 'login' },
      timeout: `${LOGIN_TIMEOUT_S}s`,
    }
  );
  recordResponse(res, 'login', number);

  if (res.status === 429) {
    fail(`Login for ${email} got 429 from the auth throttle (D-26, 20/min per address). ` +
         'The run is INVALID. Restart the server so its counters start empty, and do not ' +
         'log in from a browser while setup() runs.');
  }
  if (!check(res, { 'login returned 200': (r) => r.status === 200 })) {
    // Stops at the first failure, so a wrong password costs one failed attempt on
    // one account, not one on each (FR-02 locks an account after five).
    fail(`Login for ${email} failed with status ${res.status}: ${res.body}. ` +
         'Check TEST_PASSWORD equals LOAD_TEST_PASSWORD, and that ' +
         'manage.py create_load_test_users --count 21 has been run.');
  }
  let role = null;
  try {
    role = res.json('role');
  } catch (e) {
    role = null;
  }
  if (!check(res, { 'login account is an Employee': () => role === EXPECTED_ROLE })) {
    fail(`${email} logged in as "${role}", not ${EXPECTED_ROLE}. Every load-test account is an Employee.`);
  }

  const cookies = {};
  for (const name in res.cookies) {
    cookies[name] = res.cookies[name][0].value;
  }
  if (!cookies.csrftoken || !cookies.sessionid) {
    fail(`Login for ${email} succeeded but did not set both sessionid and csrftoken.`);
  }
  return { account: number, cookies };
}

// Logs each account in, LOGIN_SPACING_S apart start to start (D-82 rule 2).
// Call from setup() only.
export function loginAccounts(numbers) {
  const sessions = [];
  numbers.forEach((number, i) => {
    const started = Date.now();
    sessions.push(loginAccount(number));
    if (i < numbers.length - 1) paceFrom(started, LOGIN_SPACING_S);
  });
  return sessions;
}

// The session for this VU: VU n uses account n (exec.vu.idInTest). A VU with no
// account of its own stops the test rather than borrowing another's session.
export function sessionForThisVu(sessions) {
  const n = exec.vu.idInTest;
  const session = sessions[n - 1];
  if (!session || session.account !== n) {
    exec.test.abort(`VU ${n} has no load-test account of its own (D-82 rule 1). ` +
                    `${sessions.length} sessions were logged in.`);
  }
  return session;
}

// Untimed warm-up asks, tagged 'warmup' so they are not measured. They are paced
// like any other ask from the account, because they count against its ask rate.
export function warmUp(session, floorSeconds) {
  for (let i = 0; i < WARMUP_ASKS; i++) {
    const started = Date.now();
    ask(session, QUESTIONS[0], 'warmup');
    paceFrom(started, floorSeconds);
  }
}

// The worst case for setup(): every login and warm-up ask runs to its timeout or
// its pacing, whichever is longer, plus a minute for everything else.
export function setupTimeoutSeconds(logins, warmupFloorSeconds) {
  return logins * Math.max(LOGIN_SPACING_S, LOGIN_TIMEOUT_S) +
         WARMUP_ASKS * Math.max(warmupFloorSeconds, ASK_TIMEOUT_S) +
         60;
}

// --- Requests -------------------------------------------------------------------

// Same question order every run and every phase, so runs are comparable.
// Only call this from a scenario function, never from setup().
export function nextQuestion() {
  return QUESTIONS[exec.scenario.iterationInTest % QUESTIONS.length];
}

// name is 'ask' for measured requests and 'warmup' for untimed ones.
export function ask(session, question, name = 'ask') {
  const res = http.post(
    `${BASE_URL}/api/ask`,
    JSON.stringify({ question }),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': session.cookies.csrftoken,
      },
      // Request-scoped, so they go on every request: k6 empties each VU's
      // cookie jar at the start of every iteration.
      cookies: session.cookies,
      tags: { name },
      timeout: `${ASK_TIMEOUT_S}s`,
    }
  );
  recordResponse(res, name, session.account);
  return res;
}

export function isValidReply(res) {
  if (res.status !== 200) return false;
  try {
    return res.json('answered') !== undefined;
  } catch (e) {
    return false;
  }
}

export function wasAnswered(res) {
  try {
    return res.json('answered') === true;
  } catch (e) {
    return false;
  }
}

// --- The validity gate -------------------------------------------------------------
// A run counts only if this returns no problems. It reports three kinds, each in
// its own words: any 429 (D-82 rule 5), a missing commit SHA (rule 7), and each
// validity threshold not met. The latency limits are deliberately not in it: a
// valid run that is too slow is a FAIL, not an invalid run.
//
// thresholds: [[metricName, expression], ...] that must each have passed.
export function validityProblems(data, thresholds) {
  const problems = [];
  const throttled = throttleCounts(data);
  if (throttled.total === null) {
    problems.push('no responses were recorded, so the 429 count is unknown');
  } else if (throttled.total > 0) {
    problems.push(
      `${throttled.total} response(s) were 429: ${throttled.rate_limit} over a rate limit, ` +
      `${throttled.ask_in_flight} ask_in_flight. Any 429 invalidates the run (D-82 rule 5). ` +
      'A rate-limit 429 means an account went over D-79 or D-26: was the server restarted ' +
      'before this run? An ask_in_flight 429 follows an ask k6 abandoned at its timeout.'
    );
  }
  if (!SHA_PATTERN.test(GIT_SHA)) {
    problems.push('no commit SHA was recorded (-e GIT_SHA)');
  }
  for (const [metric, expression] of thresholds) {
    const result = data.metrics[metric]?.thresholds?.[expression];
    if (!result) {
      problems.push(`threshold ${metric} ${expression} was not evaluated`);
    } else if (result.ok !== true) {
      problems.push(`threshold ${metric} ${expression} was not met`);
    }
  }
  return problems;
}

export function throttleCounts(data) {
  const total = data.metrics.http_429 ? data.metrics.http_429.values.count : null;
  const inFlight = data.metrics.http_429_ask_in_flight
    ? data.metrics.http_429_ask_in_flight.values.count : 0;
  return {
    total,
    ask_in_flight: inFlight,
    rate_limit: total === null ? null : total - inFlight,
  };
}
