/**
 * The password policy, in one place (FR-01).
 *
 * FR-01 states the rules twice, once for each side: the front end shows
 * "must contain 1 uppercase letter, 1 number, 1 special character, minimum 8
 * characters" as the user types, and the server enforces "min 8 chars,
 * 1 uppercase, 1 number, 1 special character" (docs/api-contract.md, FR-01
 * password complexity). The two must be the same rules or the form will enable
 * its submit button for a password the server then rejects.
 *
 * This module is the client's only copy. Nothing else in the front end may
 * re-test a password: import `evaluatePassword` or `PASSWORD_RULES` instead.
 *
 * The server's copy is `apps/accounts/validators.py` `ComplexityValidator`, whose
 * numbers and character set come from `apps/core/constants.py`. The three
 * conditions below mirror it deliberately:
 *
 * - special character: exactly Python's `string.punctuation`, tested by set
 *   membership as the server tests it. **Whitespace is not special** — a password
 *   whose only non-alphanumeric character is a space passes a "not a letter or a
 *   digit" test but fails the server, which is the drift this note exists to stop.
 * - uppercase and number: the server counts with `str.isupper()` and
 *   `str.isdigit()`, which are Unicode-aware, so these use Unicode property
 *   escapes rather than `[A-Z]` and `[0-9]`. A residue remains for exotic input —
 *   `str.isdigit()` also accepts characters such as "²", which `\p{Nd}` does not —
 *   and it errs towards the client refusing a password the server would take,
 *   never towards enabling submit for one it would reject.
 *
 * If the server's set changes, change it here and nowhere else.
 */

/** FR-01: "minimum 8 characters". `PASSWORD_MINIMUM_LENGTH` on the server. */
export const PASSWORD_MIN_LENGTH = 8

/**
 * `PASSWORD_SPECIAL_CHARACTERS` on the server: `frozenset(string.punctuation)`,
 * the 32 ASCII punctuation characters, in Python's own order.
 */
export const PASSWORD_SPECIAL_CHARACTERS = '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'

const UPPERCASE = /\p{Uppercase}/u
const NUMBER = /\p{Nd}/u
const hasSpecialCharacter = (password) =>
  Array.from(password).some((character) => PASSWORD_SPECIAL_CHARACTERS.includes(character))

/**
 * Each rule as the user sees it, paired with the test that decides it.
 * `label` is written to read after "Password " for the screen-reader summary
 * and to stand alone in the visible list.
 */
export const PASSWORD_RULES = [
  {
    id: 'length',
    label: `At least ${PASSWORD_MIN_LENGTH} characters`,
    // Code points, not UTF-16 code units. An astral character such as an emoji is
    // two units to JavaScript and one character to Python's len(), so counting
    // units let a short emoji password enable submit and then fail server-side.
    // Every other rule in this module already iterates with Array.from.
    test: (password) => Array.from(password).length >= PASSWORD_MIN_LENGTH,
  },
  {
    id: 'uppercase',
    label: 'At least 1 uppercase letter',
    test: (password) => UPPERCASE.test(password),
  },
  {
    id: 'number',
    label: 'At least 1 number',
    test: (password) => NUMBER.test(password),
  },
  {
    id: 'special',
    // The set is named rather than merely illustrated, because the one mistake
    // it has to prevent is a user reaching for the space bar.
    label: 'At least 1 special character, such as ! # ? or $ (a space does not count)',
    test: (password) => hasSpecialCharacter(password),
  },
]

/** Strength bands, named so the meter is never read by colour alone. */
const STRENGTH_LABELS = {
  none: 'Not started',
  weak: 'Weak',
  fair: 'Fair',
  strong: 'Strong',
}

function strengthFor(password, metCount) {
  if (!password) return 'none'
  if (metCount <= 1) return 'weak'
  if (metCount < PASSWORD_RULES.length) return 'fair'
  return 'strong'
}

/**
 * Evaluate a password against every rule.
 *
 * @param {string} password
 * @returns {{
 *   results: {id: string, label: string, met: boolean}[],
 *   metCount: number,
 *   total: number,
 *   allMet: boolean,
 *   strength: 'none' | 'weak' | 'fair' | 'strong',
 *   strengthLabel: string,
 *   summary: string,
 * }}
 */
export function evaluatePassword(password = '') {
  const value = password ?? ''
  const results = PASSWORD_RULES.map((rule) => ({
    id: rule.id,
    label: rule.label,
    met: rule.test(value),
  }))
  const metCount = results.filter((result) => result.met).length
  const total = results.length
  const strength = strengthFor(value, metCount)
  const strengthLabel = STRENGTH_LABELS[strength]
  return {
    results,
    metCount,
    total,
    allMet: metCount === total,
    strength,
    strengthLabel,
    // The text equivalent of the meter (WCAG 2.1 SC 1.1.1) and the text the
    // live region announces as the user types.
    summary: `Password strength: ${strengthLabel}. ${metCount} of ${total} requirements met.`,
  }
}

/** True when the password satisfies every rule the server also enforces. */
export function passwordMeetsPolicy(password) {
  return evaluatePassword(password).allMet
}
