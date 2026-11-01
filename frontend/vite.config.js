/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * The API base the build may bake in: a path on the page's own origin, or nothing
 * (src/api/client.js then uses `/api`).
 *
 * Stage 5 item 9: the alpha serves the built SPA and `/api` from one origin
 * (D-21, D-64). Pointed at another origin, the session and CSRF cookies, which are
 * SameSite=Lax and sent `credentials: "same-origin"`, never reach the API, so login
 * would appear to succeed and every call after it would fail. A relative path
 * without its leading slash is refused as well, because it resolves against the
 * page's path: on a deep link such as `/documents/<id>` it would send every request
 * to `/documents/api/...`. Either is a build that fails here rather than a bundle
 * that fails in the browser.
 *
 * @param {string|undefined} value `VITE_API_BASE_URL` as the build would read it.
 * @returns {string|undefined} the value, unchanged, when it is acceptable.
 */
export function sameOriginApiBase(value) {
  if (value === undefined || value === '') return value
  // One leading slash and no second: `//host/api` is another origin, protocol-relative.
  if (!/^\/(?!\/)/.test(value)) {
    throw new Error(
      `VITE_API_BASE_URL must be a path on this origin, such as /api, not "${value}". ` +
        'The alpha serves the SPA and the API from one origin (D-21, D-64).',
    )
  }
  return value
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Read the same files and process environment Vite injects into the bundle.
  sameOriginApiBase(loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE_URL)

  return {
    plugins: [react()],
    // Stage 5 item 9: the production build is served by Django from the API's origin
    // (D-64), which answers every path outside `/api/` with this index.html, so the
    // page can be any client route. `base` stays `/` so index.html loads its script,
    // stylesheet and favicon from the site root (`/assets/...`, `/favicon.svg`) on a
    // deep link such as `/documents/<id>`. A relative base (`./`) would resolve them
    // under the route instead. These three are the defaults, written out because the
    // server serves `dist/` at `/` and treats `dist/assets/` as content-hashed.
    base: '/',
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
    },
    server: {
      // D-21: the browser sees one origin. `/api` is forwarded to the Django
      // development server so the session cookie is same-origin and no CORS
      // configuration exists. Development only: the production build has no proxy.
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: false,
        },
      },
    },
    // Stage 5 item 4: the front-end suite. Configured here rather than in a second
    // file so the build and the tests resolve modules the same way. The tests live
    // in `tests/`, outside `src/`, so the string check over `src/` never reads the
    // sentence it asserts is absent.
    test: {
      environment: 'jsdom',
      include: ['tests/**/*.test.{js,jsx}'],
      // Blocks the network for every test: see the file.
      setupFiles: ['./tests/setup.js'],
    },
  }
})
