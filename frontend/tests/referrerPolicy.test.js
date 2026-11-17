/**
 * REF-1 (the security review of PR #119): the page sets its own referrer policy.
 *
 * D-137's reset link carries its token in the address, `/reset-password?uid=…&token=…`,
 * until the page takes it out (src/pages/ResetPassword.jsx). While it is there, the
 * page's first requests, its script, stylesheet and icon, carry the address as their
 * Referer. Same-origin, the server receives its own address; the concern is a request to
 * another origin. The protection rested on the server's `Referrer-Policy` header alone,
 * Django's default `same-origin`, which no test pinned and the Vite development server
 * does not send.
 *
 * index.html now says `same-origin` itself: a request to another origin carries no
 * Referer at all. The meta element has to come before anything the page loads, because
 * a policy set by a meta element applies to the fetches made after it is parsed.
 * tests/productionBuild.test.js holds that the built index.html keeps it there.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const INDEX = join(import.meta.dirname, '..', 'index.html')

describe('REF-1: index.html sets the same-origin referrer policy itself, ahead of anything it loads', () => {
  it('has one <meta name="referrer" content="same-origin"> in its head, before every link and script', () => {
    const page = new DOMParser().parseFromString(readFileSync(INDEX, 'utf8'), 'text/html')
    const policies = [...page.querySelectorAll('meta[name="referrer" i]')]
    expect(policies).toHaveLength(1)
    const [policy] = policies
    expect(policy.parentElement).toBe(page.head)
    expect(policy.getAttribute('content')).toBe('same-origin')

    const loads = [...page.querySelectorAll('link[href], script[src]')]
    expect(loads.length, 'the page loads its icon and its script').toBeGreaterThanOrEqual(2)
    for (const load of loads) {
      expect(Boolean(policy.compareDocumentPosition(load) & Node.DOCUMENT_POSITION_FOLLOWING), `${load.outerHTML} comes after the policy`).toBe(true)
    }
  })
})
