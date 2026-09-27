/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // D-21: the browser sees one origin. `/api` is forwarded to the Django
    // development server so the session cookie is same-origin and no CORS
    // configuration exists.
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
})
