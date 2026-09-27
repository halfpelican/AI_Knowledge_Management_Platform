/**
 * Text that was withdrawn must not be in the source the bundle is built from.
 *
 * A string check rather than a component test, because the defect it guards
 * against was never visible to one: the sentence below was corrected in
 * apps/core/constants.py and went on shipping in the built bundle from its
 * front-end copy until the 27 September audit found it (D-60). It is the
 * provenance-removed turn's old second sentence, and it was false on the paths
 * that leave no material to answer from — a failed reprocess and FR-15's deletion.
 *
 * It reads frontend/src and not frontend/dist, so it fails before a build rather
 * than after one; `npm run build` in CI makes the bundle from exactly this tree.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const WITHDRAWN = 'Ask the question again for an answer from the current material.'

const SRC = join(import.meta.dirname, '..', 'src')

function filesUnder(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? filesUnder(path) : [path]
  })
}

describe('D-60', () => {
  it('does not contain the withdrawn provenance-removed sentence anywhere in frontend/src', () => {
    const files = filesUnder(SRC)
    expect(files.length).toBeGreaterThan(0)
    const containing = files.filter((file) => readFileSync(file, 'utf8').includes(WITHDRAWN))
    expect(containing).toEqual([])
  })
})
