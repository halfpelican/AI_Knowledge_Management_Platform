import { TEXT } from '../constants.js'

/**
 * When a D-79 rate limit lets the user try again, in words: "in 45 seconds",
 * "in 12 minutes", or "later".
 *
 * `seconds` is `ApiError.retryAfter`, the 429's `Retry-After` already read as whole
 * seconds by src/api/client.js, or null where the reply carried none. It is rounded
 * up again here, to whole minutes from a minute on, so the screen never names a
 * time sooner than the one the server sent. There is no countdown: the sentence is
 * written once, when the 429 arrives, and says when rather than how long is left.
 *
 * "later" where there is nothing to go on, so nothing is promised that the reply
 * did not say. That is D-79's in-flight 429, which carries no `Retry-After`, if a
 * caller ever passes one here, and a rate 429 whose header was missing.
 *
 * Pure, with no React, so it can be exercised on its own, as src/utils/threads.js
 * is.
 *
 * @param {number|null|undefined} seconds
 * @returns {string}
 */
export function whenToRetry(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return TEXT.retryLater
  const whole = Math.ceil(seconds)
  if (whole === 0) return TEXT.retryNow
  if (whole < 60) return TEXT.retryInSeconds(whole)
  return TEXT.retryInMinutes(Math.ceil(whole / 60))
}
