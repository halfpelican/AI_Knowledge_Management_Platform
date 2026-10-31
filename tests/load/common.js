// Shared helpers for the NFR-08 and NFR-09 load tests. How to run them (through
// run.ps1, which gates on scripts/check_flm.py), and why the pacing numbers below
// are what they are: tests/load/README.md (D-82, D-83, D-84).
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

// The FLM build the run measured (D-83 decision 3) and the hash of the database
// snapshot it ran on (D-84 decisions 1 and 3), recorded in the results JSON for
// the same reason as GIT_SHA. tests/load/run.ps1 reads the first from
// `flm version` and takes the second as an argument. A run that bypasses it has
// to type both, or it is refused here.
export const FLM_VERSION = __ENV.FLM_VERSION || '';
const FLM_VERSION_PATTERN = /^v\d+\.\d+\.\d+\S*$/;
export const DB_DUMP_SHA256 = (__ENV.DB_DUMP_SHA256 || '').toLowerCase();
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

// Set only by run.ps1, and only after scripts/check_flm.py has passed (D-83
// decision 3). A run without them still runs, and is recorded INVALID, because
// nothing says the gate ran. They are a record, not a proof: anyone can type them.
const FLM_CHECK_PASSED_AT = __ENV.FLM_CHECK_PASSED_AT || '';
const FLM_CHECK_URL = __ENV.FLM_CHECK_URL || '';
// 'none' or 'present': whether run.ps1 saw uncommitted changes to tracked files,
// in which case GIT_SHA does not fully name what was run.
const GIT_TRACKED_CHANGES = __ENV.GIT_TRACKED_CHANGES || '';

// The server the run measured, its version and its thread count (D-85 decision 4).
// run.ps1 OBSERVES them before k6 starts (D-87 decision 2): scripts/server_record.py
// preflight reads the process listening on the port, its command line (and so its
// --threads) and its venv's Waitress, confirms DEBUG off from an unmatched /api/
// path, and reads the server's last start from Waitress's log. run.ps1 passes the
// observed values as SERVER, SERVER_VERSION and SERVER_THREADS, with
// SERVER_OBSERVED_BY set, and the stated ones beside them. The name is also checked
// against the Server header the logins come back with ("The server that answered",
// below). A run that did not go through run.ps1 has only what was passed, and its
// record says so.
export const SERVER = __ENV.SERVER || '';
const SERVER_PATTERN = /^[A-Za-z][\w.-]*$/;
export const SERVER_VERSION = __ENV.SERVER_VERSION || '';
const SERVER_VERSION_PATTERN = /^\d+(\.\d+)+\S*$/;
const SERVER_THREADS_TEXT = __ENV.SERVER_THREADS || '';
export const SERVER_THREADS = /^[1-9]\d{0,3}$/.test(SERVER_THREADS_TEXT) ? Number(SERVER_THREADS_TEXT) : null;
// Set only by run.ps1: the python it read the stated version from.
const SERVER_VERSION_READ_FROM = __ENV.SERVER_VERSION_READ_FROM || '';
// Set only by run.ps1, from the pre-flight (D-87 decision 2). Empty means not observed.
const SERVER_OBSERVED_BY = __ENV.SERVER_OBSERVED_BY || '';
const SERVER_VERSION_SOURCE = __ENV.SERVER_VERSION_SOURCE || '';
const SERVER_THREADS_SOURCE = __ENV.SERVER_THREADS_SOURCE || '';
const SERVER_PID = /^\d+$/.test(__ENV.SERVER_PID || '') ? Number(__ENV.SERVER_PID) : null;
const SERVER_DEBUG = __ENV.SERVER_DEBUG || '';
const SERVER_STARTED_AT = __ENV.SERVER_STARTED_AT || '';
const PREVIOUS_RUN_FILE = __ENV.PREVIOUS_RUN_FILE || '';
const PREVIOUS_RUN_ENDED_AT = __ENV.PREVIOUS_RUN_ENDED_AT || '';
const WAITRESS_LOG = __ENV.WAITRESS_LOG || '';
// What the operator stated, recorded beside what was observed.
const SERVER_STATED = __ENV.SERVER_STATED || '';
const SERVER_THREADS_STATED = /^[1-9]\d{0,3}$/.test(__ENV.SERVER_THREADS_STATED || '')
  ? Number(__ENV.SERVER_THREADS_STATED) : null;
const SERVER_VERSION_STATED = __ENV.SERVER_VERSION_STATED || '';

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
  `Set -e GIT_SHA to the commit under test (git rev-parse HEAD); got "${GIT_SHA}". ` +
  'tests/load/run.ps1 sets it.');
requireThat(FLM_VERSION_PATTERN.test(FLM_VERSION),
  `Set -e FLM_VERSION to the version \`flm version\` prints, such as v0.9.39; got "${FLM_VERSION}". ` +
  'tests/load/run.ps1 sets it, after scripts/check_flm.py passes (D-83).');
requireThat(SHA256_PATTERN.test(DB_DUMP_SHA256),
  'Set -e DB_DUMP_SHA256 to the SHA-256 of the database snapshot this run starts from, ' +
  `64 hex digits (D-84); got "${DB_DUMP_SHA256}". tests/load/run.ps1 takes it as -DbDumpSha256.`);
requireThat(SERVER_PATTERN.test(SERVER),
  `Set -e SERVER to the server under test, waitress for D-85's measured run; got "${SERVER}". ` +
  'tests/load/run.ps1 sets it.');
requireThat(SERVER_VERSION_PATTERN.test(SERVER_VERSION),
  `Set -e SERVER_VERSION to the server's version, such as 3.0.2; got "${SERVER_VERSION}". ` +
  "tests/load/run.ps1 reads it from the venv's python (D-85).");
requireThat(SERVER_THREADS !== null,
  'Set -e SERVER_THREADS to the --threads the server was started with, 24 for D-85; ' +
  `got "${SERVER_THREADS_TEXT}". tests/load/run.ps1 takes it as -ServerThreads.`);

// --- The server's limits, copied from apps/core/constants.py ------------------
// k6 cannot import Python, so these are copies. If a rate there changes, change
// it here: the pacing assertions in each script are computed from these.
export const AUTH_LIMIT = { requests: 20, windowSeconds: 60 };        // D-26, per address
export const ASK_LIMIT = { requests: 10, windowSeconds: 60 };         // D-79, per user
export const INGESTION_LIMIT = { requests: 60, windowSeconds: 3600 }; // D-79, per user

// The spacing that keeps one sequential client under a sliding-window limit of
// N requests per W seconds, however late the server stamps any one request.
//
// DRF stamps a request when its throttle runs, which is after k6 sent it. D-85
// runs Waitress with 24 threads, so with at most 20 VUs no request waits for a
// thread, as it could under Waitress's default of 4. A stamp is still late by
// however long Waitress takes to read the whole request before handing it to a
// thread, and the middleware and session lookup take before the view: small,
// but not zero, and not the same for every request. Spacing the *sends* W/N
// apart is therefore not enough: if request k was stamped later than request
// k+N, the server sees them less than W apart and the (N+1)th is a 429. What
// does hold, whatever the thread count, because a VU sends nothing until its
// previous reply is back, is
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
//
// Under D-85's 24 threads every VU's ask is inside the server at once, so the
// queue for the NPU is inside the server's calls to FLM rather than in front of
// Waitress, and FLM sees one request per VU at a time (20 in NFR-09's load
// phase) instead of at most 4, which nothing has measured FLM doing. The
// wait then counts against each generation attempt's own 300 s as well as this.
// That moves where the time is spent, not how much there is, so this stays; but
// a server-side attempt that times out is retried, which adds NPU work for the
// asks behind it.
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
// Every response passes through recordResponse(), which adds 0 or 1 to http_429,
// so that counter exists whenever any response was seen. Its absence therefore
// means nothing was recorded, and the gate treats that as invalid rather than as
// zero.
//
// Any 429 makes the run INVALID, but each kind has its own cause, so each is
// counted by what the server put in it (apps/api/views.py) and named apart:
//   ask_in_flight        body code "ask_in_flight", no Retry-After (D-79): the
//                        account asked while its previous ask was still being
//                        answered, which follows an ask k6 abandoned at its timeout.
//   ingestion_in_flight  body code "ingestion_in_flight", no Retry-After (D-85): the
//                        account uploaded while its previous upload was still being
//                        processed, which follows an upload k6 abandoned.
//   rate_limit           DRF's throttle: no code, and a Retry-After header (D-26,
//                        D-79). An account went over a rate.
//   unrecognised         anything else. Not counted itself: it is the total less the
//                        three above, so no 429 can go uncounted.
const http429 = new Counter('http_429');
const http429RateLimit = new Counter('http_429_rate_limit');
const http429AskInFlight = new Counter('http_429_ask_in_flight');
const http429IngestionInFlight = new Counter('http_429_ingestion_in_flight');

export const ASK_IN_FLIGHT_CODE = 'ask_in_flight';
export const INGESTION_IN_FLIGHT_CODE = 'ingestion_in_flight';

export function classify429(res) {
  let code = '';
  try {
    code = res.json('code') || '';
  } catch (e) {
    code = '';
  }
  const retryAfter = (res.headers && res.headers['Retry-After']) || '';
  const kind = code === ASK_IN_FLIGHT_CODE ? 'ask_in_flight'
    : code === INGESTION_IN_FLIGHT_CODE ? 'ingestion_in_flight'
    : !code && retryAfter ? 'rate_limit'
    : 'unrecognised';
  return { kind, code, retryAfter };
}

export function recordResponse(res, name, account) {
  const throttled = res.status === 429;
  http429.add(throttled ? 1 : 0);
  if (!throttled) return;
  const c = classify429(res);
  if (c.kind === 'rate_limit') http429RateLimit.add(1);
  else if (c.kind === 'ask_in_flight') http429AskInFlight.add(1);
  else if (c.kind === 'ingestion_in_flight') http429IngestionInFlight.add(1);
  console.warn(
    `429 ${c.kind} on ${name} for ${accountEmail(account)} ` +
    `(code ${c.code || 'none'}, Retry-After ${c.retryAfter || 'none'}): this run is INVALID (D-82 rule 5).`
  );
}

// --- The server that answered (D-85 decision 4) -------------------------------------
// The one part of the server record that is observed rather than stated. Waitress
// names itself in a Server response header, "waitress"; Django's runserver sends
// "WSGIServer/0.2 CPython/3.12...". setup() keeps the header each login came back
// with, k6 hands setup()'s return value to handleSummary() as data.setup_data, and
// the gate compares the header's product name with SERVER. It shows which software
// answered. It cannot show the version or the thread count: Waitress sends neither.
export function serverProduct(headerValue) {
  return String(headerValue).trim().split(/[\/\s]/)[0].toLowerCase();
}

// For setup() to return as observed_server, beside the sessions.
export function observedServer(sessions) {
  const values = [];
  let withoutHeader = 0;
  for (const s of sessions) {
    if (s.server_header === null) withoutHeader += 1;
    else if (!values.includes(s.server_header)) values.push(s.server_header);
  }
  const observed = { logins: sessions.length, without_header: withoutHeader, values };
  const problem = serverHeaderProblem(observed);
  if (problem) {
    // INVALID already; said now so the operator can stop the run rather than wait for it.
    console.warn(`Server header at login: ${problem}. This run will be INVALID; stop it with Ctrl+C.`);
  } else {
    console.log(`Server header at login: "${values.join('", "')}" on all ${sessions.length} logins (stated: ${SERVER}).`);
  }
  return observed;
}

function serverHeaderProblem(observed) {
  if (observed.logins === 0) return 'no login was made, so no Server header was seen';
  if (observed.without_header > 0) {
    return `${observed.without_header} of ${observed.logins} logins came back with no Server header, ` +
           'so they do not show which server answered';
  }
  const others = observed.values.filter((v) => serverProduct(v) !== SERVER.toLowerCase());
  if (others.length > 0) {
    return `setup()'s logins were answered by a server calling itself "${others.join('", "')}", not the ` +
           `stated "${SERVER}" (Django's runserver calls itself WSGIServer), so this run did not ` +
           "measure D-85's server";
  }
  return null;
}

function observedFrom(data) {
  if (!data.setup_data) return { observed: null, problem: 'k6 passed no setup_data to handleSummary()' };
  const observed = data.setup_data.observed_server;
  if (!observed) return { observed: null, problem: 'setup() returned no observed_server' };
  return { observed, problem: serverHeaderProblem(observed) };
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
  const server = res.headers['Server'];
  return { account: number, cookies, server_header: server === undefined ? null : String(server) };
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

// --- What the run measured ---------------------------------------------------------
// The commit, the FLM build, the gate's result, the database snapshot and the
// server, for the results JSON (D-82 rule 7, D-83 decision 3, D-84 decision 3,
// D-85 decision 4, D-87 decision 2). null where a value was not given, so a missing one cannot read
// as recorded. data is handleSummary()'s, for the Server header setup() observed.
export function runRecord(data) {
  const { observed } = observedFrom(data);
  return {
    commit_sha: GIT_SHA || null,
    uncommitted_tracked_changes:
      GIT_TRACKED_CHANGES === 'present' ? true : GIT_TRACKED_CHANGES === 'none' ? false : null,
    flm_version: FLM_VERSION || null,
    flm_check: FLM_CHECK_PASSED_AT
      ? { result: 'PASS', script: 'scripts/check_flm.py', at: FLM_CHECK_PASSED_AT,
          against: FLM_CHECK_URL || null, by: 'tests/load/run.ps1' }
      : null,
    db_dump_sha256: DB_DUMP_SHA256 || null,
    server: SERVER || null,
    server_version: SERVER_VERSION || null,
    server_threads: SERVER_THREADS,
    // Observed by run.ps1's pre-flight (D-87 decision 2); null when not observed.
    server_pid: SERVER_PID,
    server_debug: SERVER_DEBUG || null,
    server_started_at: SERVER_STARTED_AT || null,
    previous_run: PREVIOUS_RUN_FILE
      ? { file: PREVIOUS_RUN_FILE === 'none' ? null : PREVIOUS_RUN_FILE,
          ended_at: PREVIOUS_RUN_ENDED_AT === 'none' ? null : (PREVIOUS_RUN_ENDED_AT || null) }
      : null,
    // What the operator stated, beside what was observed. null when nothing was observed:
    // then server, server_version and server_threads are themselves as passed.
    server_stated: SERVER_OBSERVED_BY
      ? { server: SERVER_STATED || null, threads: SERVER_THREADS_STATED,
          version: SERVER_VERSION_STATED || null, version_read_from: SERVER_VERSION_READ_FROM || null }
      : null,
    // The Server header setup()'s logins came back with: the distinct values, and
    // how many logins had none. null when it was not recorded.
    server_observed: observed
      ? { values: observed.values, logins: observed.logins, without_header: observed.without_header,
          matches_server: serverHeaderProblem(observed) === null }
      : null,
    // How each was known.
    server_sources: {
      server: SERVER_OBSERVED_BY
        ? `observed by ${SERVER_OBSERVED_BY}: the command line of the process listening on the ` +
          `port${SERVER_PID === null ? '' : ` (pid ${SERVER_PID})`}; also checked against server_observed`
        : 'as passed with -e SERVER, not observed: the run did not go through tests/load/run.ps1; ' +
          'checked against server_observed',
      server_version: SERVER_OBSERVED_BY
        ? `observed: ${SERVER_VERSION_SOURCE || 'source not recorded'}`
        : 'as passed with -e SERVER_VERSION, not observed',
      server_threads: SERVER_OBSERVED_BY
        ? `observed: ${SERVER_THREADS_SOURCE || 'source not recorded'} of the listening process ` +
          '(D-87 decision 2: a missing --threads is read as Waitress\'s default, 4)'
        : 'as passed with -e SERVER_THREADS, not observed',
      server_debug: SERVER_OBSERVED_BY
        ? "observed: an unmatched /api/ path got handler404's JSON 404 (D-87 decision 2)"
        : 'not observed',
      server_started_at: SERVER_OBSERVED_BY
        ? "the last 'Serving on' line in Waitress's log before the run (D-87 decision 3)"
        : 'not observed',
      server_observed: "the Server response header on setup()'s logins. It shows which software " +
                       'answered, not its version or its thread count',
    },
    // run.ps1 replaces this after k6 exits with the log's lines from the run's window
    // (D-87 decision 3). Left as it is, nothing copied the run's queueing.
    waitress_log: WAITRESS_LOG
      ? { path: WAITRESS_LOG, queue_depth: "not added: tests/load/run.ps1 adds Waitress's log for " +
          "the run's window after k6 exits, and did not" }
      : null,
  };
}

// The same record, as summary lines. label is padded by the caller.
export function runRecordLines(label, data) {
  const r = runRecord(data);
  const o = r.server_observed;
  const observedLine = !o ? 'NOT RECORDED'
    : o.without_header > 0 ? `NO Server header on ${o.without_header} of ${o.logins} logins`
    : `"${o.values.join('", "')}" on ${o.logins} logins` +
      (o.matches_server ? ', matching the stated server' : `, NOT the stated ${r.server}`);
  const changes = r.uncommitted_tracked_changes === null ? 'not recorded'
    : r.uncommitted_tracked_changes ? 'UNCOMMITTED CHANGES to tracked files'
    : 'no uncommitted changes to tracked files';
  const check = r.flm_check
    ? `check_flm.py PASS at ${r.flm_check.at} against ${r.flm_check.against || 'an unreported URL'}`
    : 'check_flm.py NOT RECORDED as run';
  const threads = r.server_threads === null ? 'threads not recorded'
    : SERVER_OBSERVED_BY ? `${r.server_threads} threads, observed (${SERVER_THREADS_SOURCE || 'source not recorded'})`
    : `${r.server_threads} threads, as passed, NOT observed`;
  const debug = !SERVER_OBSERVED_BY ? 'DEBUG not checked'
    : r.server_debug === 'off' ? 'DEBUG off' : `DEBUG NOT confirmed off (${r.server_debug || 'not recorded'})`;
  const stated = r.server_stated
    ? `${label('server, stated')}${r.server_stated.server || 'not recorded'} ` +
      `${r.server_stated.version || '(version not recorded)'}; ${r.server_stated.threads} threads\n`
    : '';
  const previous = !r.previous_run ? 'not recorded'
    : r.previous_run.file ? `${r.previous_run.ended_at} (${r.previous_run.file})` : 'none recorded';
  const started = r.server_started_at
    ? `${label('server started')}${r.server_started_at}, after the previous run's end: ${previous}\n`
    : '';
  return (
    `${label('commit')}${r.commit_sha || 'not recorded'} (${changes})\n` +
    `${label('FLM')}${r.flm_version || 'not recorded'}; ${check}\n` +
    `${label('DB snapshot SHA-256')}${r.db_dump_sha256 || 'not recorded'}\n` +
    `${label('server')}${r.server || 'not recorded'} ${r.server_version || '(version not recorded)'}; ${threads}; ${debug}\n` +
    stated +
    started +
    `${label('server, observed')}${observedLine}\n`
  );
}

// --- The validity gate -------------------------------------------------------------
// A run counts only if this returns no problems. It reports each kind in its own
// words: each kind of 429 (D-82 rule 5), a missing commit SHA (rule 7), a missing
// FLM version, snapshot hash or gate result (D-83 decision 3, D-84 decision 3), a
// missing server, server version or thread count, a Server header at login that is
// missing or names another server (D-85 decision 4), a server not observed before
// the run or DEBUG not confirmed off (D-87 decision 2), and each validity threshold
// not met. The latency limits are deliberately not in it: a valid run that is too
// slow is a FAIL, not an invalid run. run.ps1 adds more after k6 exits: a restart
// during the run, or another process listening at its end (D-87 decisions 1 and 3).
//
// thresholds: [[metricName, expression], ...] that must each have passed.
export function validityProblems(data, thresholds) {
  const problems = [];
  const throttled = throttleCounts(data);
  if (throttled.total === null) {
    problems.push('no responses were recorded, so the 429 count is unknown');
  } else {
    problems.push(...throttleProblems(throttled));
  }
  const server = observedFrom(data);
  if (server.problem) {
    problems.push(
      `the Server header at login does not show the stated server: ${server.problem} (D-85). ` +
      'This checks only which software answered, not its version or its thread count.'
    );
  }
  if (!SERVER_OBSERVED_BY) {
    problems.push(
      'the server was not observed before the run (no -e SERVER_OBSERVED_BY), so server, ' +
      'server_version and server_threads are as passed, and nothing confirmed DEBUG off or a ' +
      'restart since the previous run (D-87 decision 2). Run it through tests/load/run.ps1.'
    );
  } else if (SERVER_DEBUG !== 'off') {
    problems.push(
      `DEBUG was not confirmed off before the run: -e SERVER_DEBUG is "${SERVER_DEBUG}", not "off" ` +
      '(D-87 decision 2).'
    );
  }
  if (!SHA_PATTERN.test(GIT_SHA)) {
    problems.push('no commit SHA was recorded (-e GIT_SHA)');
  }
  if (!FLM_VERSION_PATTERN.test(FLM_VERSION)) {
    problems.push('no FLM version was recorded (-e FLM_VERSION)');
  }
  if (!SHA256_PATTERN.test(DB_DUMP_SHA256)) {
    problems.push('no database snapshot hash was recorded (-e DB_DUMP_SHA256)');
  }
  if (!SERVER_PATTERN.test(SERVER)) {
    problems.push('no server was recorded (-e SERVER)');
  }
  if (!SERVER_VERSION_PATTERN.test(SERVER_VERSION)) {
    problems.push('no server version was recorded (-e SERVER_VERSION)');
  }
  if (SERVER_THREADS === null) {
    problems.push('no server thread count was recorded (-e SERVER_THREADS)');
  }
  if (!FLM_CHECK_PASSED_AT) {
    problems.push(
      'scripts/check_flm.py is not recorded as passing before this run, so nothing shows ' +
      "FLM's embeddings were deterministic (D-83 decision 3). Run it through tests/load/run.ps1."
    );
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

// k6 leaves a counter out of the summary until something is added to it, so an
// absent kind is 0. Every kind is null when http_429 itself is absent: nothing was
// recorded at all.
export function throttleCounts(data) {
  const count = (name) => (data.metrics[name] ? data.metrics[name].values.count : 0);
  const total = data.metrics.http_429 ? data.metrics.http_429.values.count : null;
  if (total === null) {
    return { total: null, rate_limit: null, ask_in_flight: null, ingestion_in_flight: null, unrecognised: null };
  }
  const rateLimit = count('http_429_rate_limit');
  const askInFlight = count('http_429_ask_in_flight');
  const ingestionInFlight = count('http_429_ingestion_in_flight');
  return {
    total,
    rate_limit: rateLimit,
    ask_in_flight: askInFlight,
    ingestion_in_flight: ingestionInFlight,
    unrecognised: total - rateLimit - askInFlight - ingestionInFlight,
  };
}

// One reason per kind of 429 present, each in its own words.
function throttleProblems(t) {
  const problems = [];
  const invalid = 'Any 429 invalidates the run (D-82 rule 5).';
  if (t.rate_limit > 0) {
    problems.push(
      `${t.rate_limit} response(s) were 429 from a rate limit (DRF's throttle: no code, with ` +
      "Retry-After). An account went over D-79's or D-26's rate. Was the server restarted before " +
      `this run, and was nobody logging in from a browser on this machine? ${invalid}`
    );
  }
  if (t.ask_in_flight > 0) {
    problems.push(
      `${t.ask_in_flight} response(s) were 429 ask_in_flight: an account asked while its previous ` +
      `ask was still being answered (D-79). That follows an ask k6 abandoned at its ${ASK_TIMEOUT_S} s ` +
      `timeout while the server was still answering it. ${invalid}`
    );
  }
  if (t.ingestion_in_flight > 0) {
    problems.push(
      `${t.ingestion_in_flight} response(s) were 429 ingestion_in_flight: an account uploaded while ` +
      'its previous upload was still being processed (D-85). That follows an upload k6 abandoned ' +
      `at its timeout while the server was still ingesting it. ${invalid}`
    );
  }
  if (t.unrecognised > 0) {
    problems.push(
      `${t.unrecognised} response(s) were 429 of no kind these scripts know: no ask_in_flight or ` +
      "ingestion_in_flight code, and not DRF's throttle (no code, with Retry-After). The console " +
      `names each one with its code and Retry-After. ${invalid}`
    );
  }
  return problems;
}
