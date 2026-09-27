import { describe, expect, it } from 'vitest'
import { DOCUMENT_STATUS } from '../src/constants.js'
import { canReprocess } from '../src/utils/documentStatus.js'

describe('D-51', () => {
  it('does not offer the retry for "Too large to index"', () => {
    // The regression a Stage 4 commit introduced and pytest could not see: the
    // server accepts the reprocess and fails it again at the same point, so the
    // front end is the only place the affordance can be withheld.
    expect(DOCUMENT_STATUS.tooLargeToIndex).toBe('Too large to index')
    expect(canReprocess(DOCUMENT_STATUS.tooLargeToIndex)).toBe(false)
  })
})
