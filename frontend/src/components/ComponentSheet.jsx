import { useState } from 'react'
import { messageForStatus } from '../api/client.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { contrastRatio } from '../utils/contrast.js'
import Button from './Button.jsx'
import Notice from './Notice.jsx'
import TextInput from './TextInput.jsx'
import './ComponentSheet.css'

const COLOR_TOKENS = [
  '--color-surface',
  '--color-surface-alt',
  '--color-text',
  '--color-text-muted',
  '--color-primary',
  '--color-primary-hover',
  '--color-primary-text',
  '--color-border',
  '--color-border-strong',
  '--color-danger',
  '--color-danger-surface',
  '--color-success',
  '--color-success-surface',
  '--color-warning',
  '--color-warning-surface',
  '--color-focus',
]

const SPACING_TOKENS = ['--space-1', '--space-2', '--space-3', '--space-4', '--space-5', '--space-6', '--space-7']

const FONT_TOKENS = ['--font-sans', '--font-mono']

const TYPE_TOKENS = ['--text-sm', '--text-base', '--text-lg', '--text-xl', '--text-2xl']

const RADIUS_TOKENS = ['--radius-sm', '--radius-md', '--radius-full']

const FOCUS_TOKENS = ['--color-focus', '--focus-ring-width', '--focus-ring-offset']

/* Text/background pairs the interface uses. AA: 4.5:1 for text, 3:1 for non-text boundaries. */
const CONTRAST_PAIRS = [
  { label: 'Body text on surface', fg: '--color-text', bg: '--color-surface', minimum: 4.5 },
  { label: 'Body text on alt surface', fg: '--color-text', bg: '--color-surface-alt', minimum: 4.5 },
  { label: 'Muted text on surface', fg: '--color-text-muted', bg: '--color-surface', minimum: 4.5 },
  { label: 'Muted text on alt surface', fg: '--color-text-muted', bg: '--color-surface-alt', minimum: 4.5 },
  { label: 'Link text on surface', fg: '--color-primary', bg: '--color-surface', minimum: 4.5 },
  { label: 'Button text on primary', fg: '--color-primary-text', bg: '--color-primary', minimum: 4.5 },
  { label: 'Button text on primary hover', fg: '--color-primary-text', bg: '--color-primary-hover', minimum: 4.5 },
  { label: 'Danger text on surface', fg: '--color-danger', bg: '--color-surface', minimum: 4.5 },
  { label: 'Danger text on danger surface', fg: '--color-danger', bg: '--color-danger-surface', minimum: 4.5 },
  { label: 'Success text on surface', fg: '--color-success', bg: '--color-surface', minimum: 4.5 },
  { label: 'Success text on success surface', fg: '--color-success', bg: '--color-success-surface', minimum: 4.5 },
  { label: 'Warning text on warning surface', fg: '--color-warning', bg: '--color-warning-surface', minimum: 4.5 },
  { label: 'Control border on surface (non-text)', fg: '--color-border-strong', bg: '--color-surface', minimum: 3 },
  { label: 'Focus ring on surface (non-text)', fg: '--color-focus', bg: '--color-surface', minimum: 3 },
]

/* Components for the M6 screens, in build order. Named here so the sheet stays the index of the design system. */
const UPCOMING = [
  'Auth: register, login, logout (FR-01, FR-02, FR-04)',
  'Role management (FR-05)',
  'Upload (FR-08)',
  'Meeting transcript ingestion (FR-09)',
  'Repository (FR-15)',
  'Search / Ask / Sources (FR-12)',
  'Assistant (FR-13)',
  'Dashboard (FR-14)',
]

const ALL_TOKENS = [
  ...new Set([...COLOR_TOKENS, ...SPACING_TOKENS, ...FONT_TOKENS, ...TYPE_TOKENS, ...RADIUS_TOKENS, ...FOCUS_TOKENS]),
]

/** Reads the live value of each custom property from the document, so the sheet never drifts from tokens.css. */
function readTokenValues(names) {
  if (typeof document === 'undefined') return {}
  const styles = getComputedStyle(document.documentElement)
  return Object.fromEntries(names.map((name) => [name, styles.getPropertyValue(name).trim()]))
}

function formatRatio(ratio) {
  return ratio === null ? 'n/a' : `${ratio.toFixed(2)}:1`
}

export default function ComponentSheet() {
  useDocumentTitle('Component sheet')
  const [values] = useState(() => readTokenValues(ALL_TOKENS))

  return (
    <div className="sheet">
      <h1>Component sheet</h1>
      <p className="sheet__lead">
        The living style guide for the platform (NFR-14). Tokens are defined once in{' '}
        <code>src/styles/tokens.css</code>; components reference them and carry no literal values. The contrast
        ratios below are computed from the live token values.
      </p>

      <section aria-labelledby="sheet-colour">
        <h2 id="sheet-colour">Colour</h2>
        <ul className="swatches">
          {COLOR_TOKENS.map((name) => (
            <li key={name} className="swatch">
              <div className="swatch__well" style={{ backgroundColor: `var(${name})` }} aria-hidden="true" />
              <div className="swatch__meta">
                <code className="swatch__name">{name}</code>
                <span className="swatch__value">{values[name]}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="sheet-contrast">
        <h2 id="sheet-contrast">Contrast</h2>
        <p>
          WCAG 2.1 AA requires 4.5:1 for text and 3:1 for non-text boundaries such as input borders and the
          focus ring. Each pair the interface uses is checked here.
        </p>
        <div className="table-scroll" role="region" aria-labelledby="sheet-contrast" tabIndex={0}>
          <table className="contrast-table">
            <caption className="visually-hidden">Contrast ratio of each text and background pair</caption>
            <thead>
              <tr>
                <th scope="col">Pair</th>
                <th scope="col">Foreground</th>
                <th scope="col">Background</th>
                <th scope="col">Ratio</th>
                <th scope="col">Minimum</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              {CONTRAST_PAIRS.map((pair) => {
                const ratio = contrastRatio(values[pair.fg], values[pair.bg])
                const passes = ratio !== null && ratio >= pair.minimum
                return (
                  <tr key={pair.label}>
                    <th scope="row">{pair.label}</th>
                    <td>
                      <code>{pair.fg}</code>
                    </td>
                    <td>
                      <code>{pair.bg}</code>
                    </td>
                    <td>{formatRatio(ratio)}</td>
                    <td>{pair.minimum}:1</td>
                    <td className={passes ? 'contrast-pass' : 'contrast-fail'}>{passes ? 'Pass' : 'Fail'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="sheet-spacing">
        <h2 id="sheet-spacing">Spacing</h2>
        <ul className="token-list">
          {SPACING_TOKENS.map((name) => (
            <li key={name} className="token-row">
              <code>{name}</code>
              <span className="spacing-bar" style={{ width: `var(${name})` }} aria-hidden="true" />
              <span className="token-row__value">{values[name]}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="sheet-type">
        <h2 id="sheet-type">Type</h2>
        <ul className="token-list">
          {FONT_TOKENS.map((name) => (
            <li key={name} className="token-row">
              <code>{name}</code>
              <span className="token-row__value">{values[name]}</span>
            </li>
          ))}
        </ul>
        <ul className="token-list">
          {TYPE_TOKENS.map((name) => (
            <li key={name} className="type-row">
              <p className="type-row__sample" style={{ fontSize: `var(${name})` }}>
                The quick brown fox jumps over the lazy dog
              </p>
              <code>{name}</code> <span className="token-row__value">{values[name]}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="sheet-radii">
        <h2 id="sheet-radii">Radii</h2>
        <ul className="token-list">
          {RADIUS_TOKENS.map((name) => (
            <li key={name} className="token-row">
              <span className="radius-box" style={{ borderRadius: `var(${name})` }} aria-hidden="true" />
              <code>{name}</code>
              <span className="token-row__value">{values[name]}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="sheet-focus">
        <h2 id="sheet-focus">Focus ring</h2>
        <p>
          Every interactive element shows the same ring on keyboard focus (<code>:focus-visible</code>), drawn
          outside the element so it always sits on the page surface. Press Tab to move through this page and
          see it on the links, buttons and inputs.
        </p>
        <ul className="token-list">
          {FOCUS_TOKENS.map((name) => (
            <li key={name} className="token-row">
              <code>{name}</code>
              <span className="token-row__value">{values[name]}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="sheet-button">
        <h2 id="sheet-button">Button</h2>
        <div className="demo-row">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button disabled>Primary disabled</Button>
          <Button variant="secondary" disabled>
            Secondary disabled
          </Button>
        </div>
      </section>

      <section aria-labelledby="sheet-text-input">
        <h2 id="sheet-text-input">Text input</h2>
        <div className="demo-stack">
          <TextInput
            label="Work email"
            hint="Use the address you registered with."
            type="email"
            name="email-demo"
            autoComplete="off"
          />
          <TextInput
            label="Work email"
            type="email"
            name="email-error-demo"
            defaultValue="not-an-address"
            error="Enter a valid email address."
            autoComplete="off"
          />
        </div>
      </section>

      <section aria-labelledby="sheet-notice">
        <h2 id="sheet-notice">Notice</h2>
        <Notice variant="info" title="Nothing here yet">
          Upload a document or add a meeting transcript to get started.
        </Notice>
        <Notice variant="error" title="Upload failed">
          Processing failed. Please try again.
        </Notice>
        <Notice variant="unavailable">{messageForStatus(503)}</Notice>
      </section>

      <section aria-labelledby="sheet-upcoming">
        <h2 id="sheet-upcoming">Still to come</h2>
        <p>Components for the M6 screens. None is implemented yet.</p>
        {UPCOMING.map((name) => (
          <h3 key={name} className="upcoming">
            {name}
          </h3>
        ))}
      </section>
    </div>
  )
}
