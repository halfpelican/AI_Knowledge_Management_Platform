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
  // FR-20's knowledge map (D-132): the four node types' fills, and the lines, all
  // on the surface the diagram and its legend sit on. Non-text, so 3:1 (SC 1.4.11).
  // tests/contrast.test.js holds that these are the fills the stylesheet declares
  // and that the four differ.
  { label: 'Map: document node on surface (non-text)', fg: '--color-primary', bg: '--color-surface', minimum: 3 },
  { label: 'Map: meeting node on surface (non-text)', fg: '--color-success', bg: '--color-surface', minimum: 3 },
  { label: 'Map: tag node on surface (non-text)', fg: '--color-warning', bg: '--color-surface', minimum: 3 },
  { label: 'Map: contributor node on surface (non-text)', fg: '--color-text-muted', bg: '--color-surface', minimum: 3 },
  { label: 'Map: selected node outline and lines on surface (non-text)', fg: '--color-text', bg: '--color-surface', minimum: 3 },
  // PR #119's screens (tokens.css, "PR #119's redesign"): a row for each colour
  // the redesign added, on what it sits on. tests/contrast.test.js holds the same.
  { label: 'Body text on page background (home, sign-in card)', fg: '--color-text', bg: '--color-background', minimum: 4.5 },
  { label: 'Heading on page background', fg: '--color-heading', bg: '--color-background', minimum: 4.5 },
  { label: 'Table title on surface', fg: '--color-heading', bg: '--color-surface', minimum: 4.5 },
  { label: 'Link on page background (sign-in card)', fg: '--color-link', bg: '--color-background', minimum: 4.5 },
  { label: 'Link on surface (dashboard panels)', fg: '--color-link', bg: '--color-surface', minimum: 4.5 },
  { label: 'Info notice text on info surface', fg: '--color-primary-hover', bg: '--color-info-surface', minimum: 4.5 },
  { label: 'Body text on info surface', fg: '--color-text', bg: '--color-info-surface', minimum: 4.5 },
  { label: 'Error notice text on danger surface', fg: '--color-danger-text', bg: '--color-danger-surface', minimum: 4.5 },
  { label: 'Status badge: Indexed; Profile role badge: Administrator', fg: '--color-status-indexed', bg: '--color-status-indexed-surface', minimum: 4.5 },
  { label: 'Status badge: every other status', fg: '--color-status-not-indexed', bg: '--color-status-not-indexed-surface', minimum: 4.5 },
  { label: 'Outline button border on page background (non-text)', fg: '--color-border-strong', bg: '--color-background', minimum: 3 },
  { label: 'Home illustration: device on page (non-text)', fg: '--color-illustration-device', bg: '--color-background', minimum: 3 },
  { label: 'Home illustration: figure on device (non-text)', fg: '--color-illustration-figure', bg: '--color-illustration-device', minimum: 3 },
  { label: 'Home illustration: bubble text on its bubble', fg: '--color-illustration-bubble-text', bg: '--color-text-muted', minimum: 4.5 },
  { label: 'Home illustration: accent shape on page (non-text)', fg: '--color-accent', bg: '--color-background', minimum: 3 },
  // The Profile page's Employee role badge, in #119's colours (FEA-7).
  { label: 'Profile role badge: Employee', fg: '--color-primary-hover', bg: '--color-role-employee-surface', minimum: 4.5 },
]
