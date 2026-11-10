/* Text/background pairs the interface uses. AA: 4.5:1 for text, 3:1 for non-text
   boundaries. In its own module so the sheet stays a pure component export (fast refresh) and tests/componentSheet.test.jsx can recompute every pair from tokens.css on disk — in the browser the sheet computes them from the live custom properties, which jsdom does not apply. */
export const CONTRAST_PAIRS = [
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
  // Pairs the screens compose: the in-page 403's link sits on the error
  // notice, field errors appear inside the dashboard's filter panel, and a
  // notice body can carry body or muted text on any notice surface. The full
  // table, generated from the stylesheets, is docs/accessibility.md;
  // tests/contrast.test.js fails a change that breaks any of it.
  { label: 'Link on danger surface (NotPermitted)', fg: '--color-primary', bg: '--color-danger-surface', minimum: 4.5 },
  { label: 'Danger text on alt surface', fg: '--color-danger', bg: '--color-surface-alt', minimum: 4.5 },
  { label: 'Muted text on danger surface', fg: '--color-text-muted', bg: '--color-danger-surface', minimum: 4.5 },
  { label: 'Muted text on warning surface', fg: '--color-text-muted', bg: '--color-warning-surface', minimum: 4.5 },
  { label: 'Invalid input border on surface (non-text)', fg: '--color-danger', bg: '--color-surface', minimum: 3 },
  { label: 'Control border on surface (non-text)', fg: '--color-border-strong', bg: '--color-surface', minimum: 3 },
  // FR-15's browse values sit in a panel on the alt surface.
  { label: 'Control border on alt surface (non-text)', fg: '--color-border-strong', bg: '--color-surface-alt', minimum: 3 },
  { label: 'Focus ring on surface (non-text)', fg: '--color-focus', bg: '--color-surface', minimum: 3 },
]
