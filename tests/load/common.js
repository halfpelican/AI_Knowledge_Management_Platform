import http from 'k6/http';
import exec from 'k6/execution';
import { check, fail } from 'k6';

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TEST_EMAIL = __ENV.TEST_EMAIL;
const TEST_PASSWORD = __ENV.TEST_PASSWORD;

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

export function loginOnce() {
  if (!TEST_EMAIL || !TEST_PASSWORD) {
    fail('Set TEST_EMAIL and TEST_PASSWORD with -e flags.');
  }

  const res = http.post(
    `${BASE_URL}/api/auth/login`,
    JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'login' } }
  );

  if (!check(res, { 'login returned 200': (r) => r.status === 200 })) {
    fail(`Login failed with status ${res.status}: ${res.body}`);
  }

  const cookies = {};
  for (const name in res.cookies) {
    cookies[name] = res.cookies[name][0].value;
  }
  if (!cookies.csrftoken) {
    fail('Login succeeded but no csrftoken cookie came back.');
  }
  return cookies;
}

// Same question order every run and every phase, so runs are comparable.
// Only call this from a scenario function, never from setup().
export function nextQuestion() {
  return QUESTIONS[exec.scenario.iterationInTest % QUESTIONS.length];
}

// name is 'ask' for measured requests and 'warmup' for untimed ones.
export function ask(cookies, question, name = 'ask') {
  return http.post(
    `${BASE_URL}/api/ask`,
    JSON.stringify({ question }),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': cookies.csrftoken,
      },
      // Request-scoped, so they go on every request: k6 empties each VU's
      // cookie jar at the start of every iteration.
      cookies,
      tags: { name },
      // Long on purpose: the single NPU queues requests, so a slow system
      // should show up as a measured FAIL, not a timeout.
      timeout: '300s',
    }
  );
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

// A run only counts if the error and checks thresholds passed.
export function runWasValid(data) {
  const failed = data.metrics['http_req_failed{name:ask}'];
  const checks = data.metrics.checks;
  return (
    failed?.thresholds?.['rate<0.01']?.ok === true &&
    checks?.thresholds?.['rate>0.99']?.ok === true
  );
}