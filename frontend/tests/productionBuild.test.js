// @vitest-environment node
/**
 * The production build, as the alpha serves it (Stage 5 item 9, D-21, D-64).
 *
 * Django serves `frontend/dist` from the API's own origin and answers every path
 * outside `/api/` with its index.html, so the page that loads the bundle can be any
 * client route. Two things only the build decides, and neither shows in the
 * development server, which serves from `/` and proxies `/api` whatever the
 * configuration says:
 *
 * - index.html names its script, stylesheet and favicon from the site root. With a
 *   relative base, a deep link such as `/documents/<id>` would ask for
 *   `/documents/assets/...`, and the page would load nothing.
 * - the API base is a path on that origin. Pointed at another, the SameSite=Lax
 *   session and CSRF cookies never reach the API: login appears to succeed and
 *   every call after it fails.
 *
 * The build runs in memory (`write: false`), so this file never touches `dist/`.
 * In the node environment, because a bundler has no business seeing jsdom's
 * `window`; tests/setup.js still blocks the network, and nothing here uses it.
 */
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { build } from 'vite'
import { afterEach, describe, expect, it, vi } from 'vitest'
import config, { sameOriginApiBase } from '../vite.config.js'

const FRONTEND = join(import.meta.dirname, '..')

/** The dev server's proxy target (vite.config.js), which the bundle must never name. */
const DEV_PROXY_TARGETS = ['127.0.0.1:8000', 'localhost:8000']

/** Every `src` and `href` in an HTML document, in order. */
function referencedUrls(html) {
  return [...html.matchAll(/\b(?:src|href)="([^"]*)"/g)].map((match) => match[1])
}

describe('the API base the build bakes in', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it.each([undefined, '', '/api', '/api/', '/kmp/api'])('accepts %j, a path on this origin', (value) => {
    expect(sameOriginApiBase(value)).toBe(value)
  })

  it.each([
    'http://127.0.0.1:8000/api',
    'https://kmp.example.com/api',
    '//127.0.0.1:8000/api',
    'api',
    './api',
  ])('refuses %j, which is another origin or resolves against the page path', (value) => {
    expect(() => sameOriginApiBase(value)).toThrow(/must be a path on this origin/)
  })

  it('fails the build when VITE_API_BASE_URL names another origin', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000/api')
    expect(() => config({ command: 'build', mode: 'production' })).toThrow(/must be a path on this origin/)
  })

  it('serves dist/ from the site root, with the hashed files under assets/', () => {
    const resolved = config({ command: 'build', mode: 'production' })
    expect(resolved.base).toBe('/')
    expect(resolved.build.outDir).toBe('dist')
    expect(resolved.build.assetsDir).toBe('assets')
  })
})

describe('the production build', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it(
    'loads its assets from the site root on any client route, and calls the API on its own origin',
    async () => {
      // Vitest sets NODE_ENV=test, and Vite builds for whatever NODE_ENV says; this is
      // the bundle `npm run build` makes.
      vi.stubEnv('NODE_ENV', 'production')
      const result = await build({
        root: FRONTEND,
        mode: 'production',
        logLevel: 'silent',
        build: { write: false },
      })
      const files = (Array.isArray(result) ? result : [result]).flatMap((bundle) => bundle.output)
      const byName = new Map(files.map((file) => [file.fileName, file]))

      const html = byName.get('index.html')
      expect(html !== undefined, 'the build emits index.html').toBe(true)
      const urls = referencedUrls(String(html.source))

      // One script and one stylesheet from assets/, and the favicon from public/.
      const assets = urls.filter((url) => url.startsWith('/assets/'))
      expect(assets.some((url) => url.endsWith('.js'))).toBe(true)
      expect(assets.some((url) => url.endsWith('.css'))).toBe(true)
      expect(urls).toContain('/favicon.svg')
      expect(existsSync(join(FRONTEND, 'public', 'favicon.svg'))).toBe(true)

      // Every reference is root-relative: one leading slash, no scheme, no host.
      for (const url of urls) {
        expect(url, `${url} resolves from the site root`).toMatch(/^\/(?!\/)/)
      }
      // ...and names a file the build emitted, apart from public/'s, copied beside them.
      for (const url of assets) {
        expect(byName.has(url.slice(1)), `${url} is in the build`).toBe(true)
      }

      const code = files
        .filter((file) => file.type === 'chunk')
        .map((file) => file.code)
        .join('\n')
      // Booleans, so a failure names the property rather than printing the bundle.
      expect(/["'`]\/api["'`]/.test(code), 'the bundle calls the API at /api').toBe(true)
      for (const target of DEV_PROXY_TARGETS) {
        expect(code.includes(target), `the bundle names ${target}`).toBe(false)
      }
    },
    30_000,
  )
})
