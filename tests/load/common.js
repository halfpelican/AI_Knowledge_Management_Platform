import http from 'k6/http';
import { check, fail } from 'k6';

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TEST_EMAIL = __ENV.TEST_EMAIL;
const TEST_PASSWORD = __ENV.TEST_PASSWORD;

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
  'What happened in the security incident debrief?',
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

let sessionApplied = false;
function applySession(cookies) {
  if (sessionApplied) return;
  const jar = http.cookieJar();
  for (const name in cookies) {
    jar.set(BASE_URL, name, cookies[name]);
  }
  sessionApplied = true;
}

export function ask(cookies) {
  applySession(cookies);
  const question = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
  return http.post(
    `${BASE_URL}/api/ask`,
    JSON.stringify({ question }),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': cookies.csrftoken,
      },
      tags: { name: 'ask' },
      timeout: '60s',
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