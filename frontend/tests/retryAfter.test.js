/**
 * When a D-79 limit says the user can try again: the 429's `Retry-After` as the
 * API client reads it, and the words the screens put it in.
 *
 * The property both halves defend is the same: the screen never names a time
 * sooner than the server sent, and names none at all where the server sent none
 * it could read.
 */
import { describe, expect, it } from 'vitest'
import { ApiError, post } from '../src/api/client.js'
import { TEXT } from '../src/constants.js'
import { whenToRetry } from '../src/utils/retryAfter.js'
import { serveApi } from './fakeApi.js'

describe('whenToRetry: Retry-After in words, rounded up', () => {
  it.each([
    [1, 'in 1 second'],
    [42, 'in 42 seconds'],
    [59, 'in 59 seconds'],
    [60, 'in 1 minute'],
    [61, 'in 2 minutes'],
    [720, 'in 12 minutes'],
    [3600, 'in 60 minutes'],
  ])('says %i seconds as "%s"', (seconds, words) => {
    expect(whenToRetry(seconds)).toBe(words)
  })

  it('promises no time where none was sent', () => {
    expect(whenToRetry(null)).toBe(TEXT.retryLater)
    expect(whenToRetry(undefined)).toBe(TEXT.retryLater)
    expect(whenToRetry(Number.NaN)).toBe(TEXT.retryLater)
  })
})

/** The ApiError `post` rejects with for one faked reply. */
async function rejectionFor(reply) {
  serveApi({ 'POST /api/ask': reply })
  try {
    await post('/ask', { question: 'Does unused annual leave carry over?' })
  } catch (error) {
    return error
  }
  throw new Error('the request did not fail')
}

describe('ApiError: what the client lifts off a 429', () => {
  it.each([
    ['30', 30],
    [' 5 ', 5],
    ['2.5', 3],
    ['Wed, 21 Oct 2026 07:28:00 GMT', null],
    ['soon', null],
  ])('reads Retry-After "%s" as %s', async (header, seconds) => {
    const error = await rejectionFor({ status: 429, body: { detail: 'Request was throttled.' }, headers: { 'Retry-After': header } })
    expect(error).toBeInstanceOf(ApiError)
    expect(error.retryAfter).toBe(seconds)
  })

  it('reads no Retry-After where none was sent, and the body\'s code where it is a string', async () => {
    const error = await rejectionFor({ status: 429, body: { detail: 'Still answering.', code: 'ask_in_flight' } })
    expect(error.retryAfter).toBeNull()
    expect(error.code).toBe('ask_in_flight')
    // The message is the client's, never the body's.
    expect(error.message).not.toContain('Still answering')
  })

  it('reads Retry-After only on a 429', async () => {
    const error = await rejectionFor({ status: 503, body: { detail: 'Service unavailable.' }, headers: { 'Retry-After': '30' } })
    expect(error.retryAfter).toBeNull()
  })
})
