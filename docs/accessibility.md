# Accessibility — the Stage 5 item 7 record

**Date:** 8 November 2026 · **Scope:** the React front end, all M6 screens ·
**Bar:** WCAG 2.1 Level AA, per NFR-16: "The web interface must conform to WCAG
2.1 Level AA, including a minimum 4.5:1 contrast ratio for normal text (SC
1.4.3) and full keyboard operability of all interactive elements (SC 2.1.1)."
NFR-17's accessible table equivalent concerns FR-20's visualisation, which is
NIT3004 scope and not yet built; nothing here claims it.

How this document stays true: every claim in it has a test named beside it, and
the tests recompute from the stylesheets on disk — jsdom applies no stylesheet,
so `frontend/tests/stylesheets.js` reads and parses every `.css` file under
`src/` instead, and `frontend/tests/stylesheets.test.js` fails the suite if a
rule exists that the reader did not account for. The interface has one theme;
there is no `prefers-color-scheme` variant, so each pair is measured once.

## 1. Contrast

Computed from the live values in `src/styles/tokens.css` with the WCAG 2.1
relative-luminance formula. The same pairs are asserted on every test run by
`frontend/tests/contrast.test.js`, which also sweeps every colour-taking
declaration in every stylesheet and fails on any colour usage the pair tables
do not account for — so this table cannot rot while the stylesheets move on.
The component sheet at `/components` renders the core of this table live
(`src/components/contrastPairs.js`), and `frontend/tests/componentSheet.test.jsx`
recomputes each of its documented pairs from the CSS on disk.

### Text (SC 1.4.3, AA 4.5:1)

| Foreground | Background | Ratio | Requires | Result | Where |
|---|---|---|---|---|---|
| `--color-text` #1f2933 | `--color-surface` #ffffff | 14.76:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-surface-alt` #f3f4f6 | 13.41:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-danger-surface` #fef3f2 | 13.57:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-success-surface` #ecfdf3 | 13.99:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-warning-surface` #fffaeb | 14.14:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text-muted` #4b5563 | `--color-surface` #ffffff | 7.56:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-surface-alt` #f3f4f6 | 6.87:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-danger-surface` #fef3f2 | 6.95:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-success-surface` #ecfdf3 | 7.17:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-warning-surface` #fffaeb | 7.24:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-primary` #1d4ed8 | `--color-surface` #ffffff | 6.70:1 | 4.5:1 | Pass | links; the in-page 403’s link sits on the error notice |
| `--color-primary` #1d4ed8 | `--color-surface-alt` #f3f4f6 | 6.09:1 | 4.5:1 | Pass | links; the in-page 403’s link sits on the error notice |
| `--color-primary` #1d4ed8 | `--color-danger-surface` #fef3f2 | 6.16:1 | 4.5:1 | Pass | links; the in-page 403’s link sits on the error notice |
| `--color-primary-hover` #1e40af | `--color-surface` #ffffff | 8.72:1 | 4.5:1 | Pass | link hover |
| `--color-primary-hover` #1e40af | `--color-surface-alt` #f3f4f6 | 7.93:1 | 4.5:1 | Pass | link hover |
| `--color-primary-hover` #1e40af | `--color-danger-surface` #fef3f2 | 8.02:1 | 4.5:1 | Pass | link hover |
| `--color-primary-text` #ffffff | `--color-primary` #1d4ed8 | 6.70:1 | 4.5:1 | Pass | button and skip-link text, the pressed facet |
| `--color-primary-text` #ffffff | `--color-primary-hover` #1e40af | 8.72:1 | 4.5:1 | Pass | button and skip-link text, the pressed facet |
| `--color-danger` #b42318 | `--color-surface` #ffffff | 6.57:1 | 4.5:1 | Pass | field errors (forms sit on the page and in the dashboard’s filter panel), failed chips, the error notice’s title |
| `--color-danger` #b42318 | `--color-surface-alt` #f3f4f6 | 5.97:1 | 4.5:1 | Pass | field errors (forms sit on the page and in the dashboard’s filter panel), failed chips, the error notice’s title |
| `--color-danger` #b42318 | `--color-danger-surface` #fef3f2 | 6.05:1 | 4.5:1 | Pass | field errors (forms sit on the page and in the dashboard’s filter panel), failed chips, the error notice’s title |
| `--color-success` #067647 | `--color-surface` #ffffff | 5.69:1 | 4.5:1 | Pass | the Indexed chip, the sheet’s pass column |
| `--color-success` #067647 | `--color-surface-alt` #f3f4f6 | 5.17:1 | 4.5:1 | Pass | the Indexed chip, the sheet’s pass column |
| `--color-success` #067647 | `--color-success-surface` #ecfdf3 | 5.40:1 | 4.5:1 | Pass | the Indexed chip, the sheet’s pass column |
| `--color-warning` #93370d | `--color-surface` #ffffff | 7.52:1 | 4.5:1 | Pass | the AI-unavailable notice’s title (NFR-19) |
| `--color-warning` #93370d | `--color-warning-surface` #fffaeb | 7.21:1 | 4.5:1 | Pass | the AI-unavailable notice’s title (NFR-19) |

### User-interface component boundaries and fills (SC 1.4.11, AA 3:1)

| Component colour | Adjacent colour | Ratio | Requires | Result | Where |
|---|---|---|---|---|---|
| `--color-border-strong` #667085 | `--color-surface` #ffffff | 4.97:1 | 3:1 | Pass | inputs, secondary buttons, chips, the drop zone, scroll-region boundaries |
| `--color-border-strong` #667085 | `--color-surface-alt` #f3f4f6 | 4.52:1 | 3:1 | Pass | inputs, secondary buttons, chips, the drop zone, scroll-region boundaries |
| `--color-focus` #1d4ed8 | `--color-surface` #ffffff | 6.70:1 | 3:1 | Pass | the focus ring, drawn with an offset onto the page or a panel |
| `--color-focus` #1d4ed8 | `--color-surface-alt` #f3f4f6 | 6.09:1 | 3:1 | Pass | the focus ring, drawn with an offset onto the page or a panel |
| `--color-primary` #1d4ed8 | `--color-surface` #ffffff | 6.70:1 | 3:1 | Pass | primary buttons, the pressed facet’s fill, the progress fill, the active drop zone, the info notice’s edge |
| `--color-primary` #1d4ed8 | `--color-surface-alt` #f3f4f6 | 6.09:1 | 3:1 | Pass | primary buttons, the pressed facet’s fill, the progress fill, the active drop zone, the info notice’s edge |
| `--color-primary-hover` #1e40af | `--color-surface` #ffffff | 8.72:1 | 3:1 | Pass | their hover fills |
| `--color-primary-hover` #1e40af | `--color-surface-alt` #f3f4f6 | 7.93:1 | 3:1 | Pass | their hover fills |
| `--color-danger` #b42318 | `--color-surface` #ffffff | 6.57:1 | 3:1 | Pass | the invalid input’s border, the failed chip’s border, the error notice’s edge |
| `--color-danger` #b42318 | `--color-surface-alt` #f3f4f6 | 5.97:1 | 3:1 | Pass | the invalid input’s border, the failed chip’s border, the error notice’s edge |
| `--color-danger` #b42318 | `--color-danger-surface` #fef3f2 | 6.05:1 | 3:1 | Pass | the invalid input’s border, the failed chip’s border, the error notice’s edge |
| `--color-success` #067647 | `--color-surface` #ffffff | 5.69:1 | 3:1 | Pass | the Indexed chip’s border |
| `--color-success` #067647 | `--color-success-surface` #ecfdf3 | 5.40:1 | 3:1 | Pass | the Indexed chip’s border |
| `--color-warning` #93370d | `--color-surface` #ffffff | 7.52:1 | 3:1 | Pass | the unavailable notice’s edge |
| `--color-warning` #93370d | `--color-warning-surface` #fffaeb | 7.21:1 | 3:1 | Pass | the unavailable notice’s edge |

### Documented exceptions

| Colour | Why no pair is required | Held by |
|---|---|---|
| `--color-border` #d0d5dd (1.47:1 on surface) | Decorative separators: table-row rules, panel outlines, the heading underline. Never the sole boundary of a control — `contrast.test.js :: never makes the decorative border the boundary of a control` fails any rule that puts it on one. The one control that had it, the Ask screen's conversation-list item, was moved to `--color-border-strong` in this pass | `tests/contrast.test.js` |
| `--color-overlay` (the modal scrim) | Decorative and `aria-hidden`; nothing is read through it. The dialogue restates its own surface and text colour, which the test asserts, because white text on the bare composite would measure about 4.05:1 | `contrast.test.js :: the modal scrim backs no text` |
| The password strength meter's fills | The bar is `aria-hidden` decoration; its text equivalent is the visible "Password strength: …" sentence (SC 1.1.1) | `tests/textEquivalents.test.jsx` |
| The button spinner (`currentColor`) | `aria-hidden` decoration; the label changes with it | `tests/textEquivalents.test.jsx` |

## 2. Focus states (SC 2.4.7)

- One global rule in `src/styles/base.css`: `:focus-visible { outline:
  var(--focus-ring); outline-offset: var(--focus-ring-offset) }` — 3px solid
  `--color-focus`, offset 2px so the ring sits on the surface around the
  control (6.70:1 on the page, 6.09:1 on panels; SC 1.4.11 asks 3:1 of it).
- The one control that cannot carry the ring itself is the drop zone's file
  input, which is visually hidden (finding 2): `FileDropZone.css` draws the
  input's ring on its label with `.dropzone__input:focus-visible +
  .dropzone__choose`.
- Tests, all in stylesheet terms since jsdom draws nothing:
  `focusStyles.test.jsx :: declares :focus-visible globally…` checks the rule's
  width, style, colour and offset; `:: never removes an outline without drawing
  a replacement in the same rule` sweeps every rule in every stylesheet for
  `outline: none` and `0`; `dropZone.test.jsx :: draws the focus ring on the
  label…` reaches the hidden input by Tab and asserts the sibling rule matches.

## 3. Tab order (SC 2.1.1, SC 2.1.2)

`frontend/tests/keyboard.js` presses Tab as a browser does (keydown first, so
the dialogue's trap can claim it; one stop per radio group; disabled controls
and closed `<details>` skipped). `frontend/tests/tabOrder.test.jsx` walks
sign-in, dashboard, documents, upload, meetings and ask end to end and asserts,
on every screen:

- the skip link is the first stop, hidden until focused and shown the moment it
  is (`focusStyles.test.jsx` holds the hiding to the `:not(:focus)` rule);
- no positive `tabindex` anywhere — the DOM order is the tab order, which is
  what lets the Ask screen's two-column layout collapse to one column without
  reordering (the aside is after the main column in the DOM);
- nothing reachable is invisible while it holds focus, checked against the
  stylesheets through `tests/stylesheets.js`;
- no trap: the walk fails if focus revisits a stop before leaving the page, and
  the delete confirmation's Tab cycle is tested inside the dialogue both ways;
- the table region that scrolls at narrow widths is itself a stop
  (`tabIndex=0`, `role="region"`, named), ahead of the rows inside it, so the
  sideways scroll is keyboard-operable.

## 4. Text equivalents (SC 1.1.1)

The interface has no images or canvas charts; its non-text content is bars,
glyphs and markers, and each carries its information as text
(`frontend/tests/textEquivalents.test.jsx`):

| Non-text content | Text equivalent |
|---|---|
| Upload progress bar | `role="progressbar"` named for its file, `aria-valuenow` and `aria-valuetext`, the visible percentage beside the track; an indeterminate bar carries no value — zero would read as "no progress" — and says what it is doing |
| Browse facet count | The button's name is "Finance 3 documents": the bare number is `aria-hidden`, the counted noun visually hidden |
| Sort direction arrow | ", sorted ascending/descending" in the button's name; `aria-sort` on the column; the arrow is `aria-hidden` |
| Citation marker [1] | Accessible name "Source for statement 1"; the bracket is `aria-hidden` |
| Button spinner | `aria-busy`, spinner `aria-hidden`, and the label changes ("Signing in…") |
| Password strength meter | The visible "Password strength: …" sentence; each rule carries a hidden "Met:"/"Not met:" prefix so state is never colour alone (SC 1.4.1) |
| Dashboard totals | Figures are `<dd>` values whose `<dt>` labels sit beside them in the same definition list |

The sweep in the same file asserts no `aria-hidden` subtree contains a
focusable element, and the tab-order walk cannot visit one (an `aria-hidden`
ancestor is a hiding cause).

## 5. Reflow (SC 1.4.10) — usability finding 6's check

Measured in headless Edge 157 with the real stylesheets, the application inside
a 320-CSS-px iframe (headless Edge will not open a window that narrow), a faked
API and a seeded repository. `documentElement.clientWidth` vs `scrollWidth`,
8 November 2026:

| Route | 320 px | Notes |
|---|---|---|
| /login, /register | 305 / 305 | no sideways scroll |
| /dashboard | 305 / 305 | panels stack to one column |
| /documents | **305 / 305 after the fix** (375 / 305 before) | see below |
| /upload | 305 / 305 | drop zone 273×206 px — a target, not a strip |
| /meetings | 305 / 305 | with the attendee picker |
| /ask | 305 / 305 | acknowledgement line visible, 24 px reserved |
| /search, /admin/roles | 320 / 320 | fit without a vertical scrollbar |
| /components | 305 / 305 | the one flagged element was the indeterminate bar's band mid-`translateX` inside the track's `overflow: hidden` — a measuring artefact, not page overflow |
| /documents at 1280 px | 1265 / 1265 | the table fits whole (region 1120 / 1120); the retry button in view |

**The defect found and fixed:** at 320 px the /documents page scrolled sideways
by 70 px under content that painted nothing. The sortable heading's
visually-hidden ", sorted descending" span is absolutely positioned; with no
positioned ancestor its containing block was the page, so its static position
escaped the `.table-scroll` clip and widened the document. Fix: `position:
relative` on `.table-scroll` (src/styles/base.css), which makes the scroller
the containing block. Guard: `focusStyles.test.jsx :: anchors .table-scroll…`.

The data table itself still scrolls sideways inside its labelled,
keyboard-focusable region at narrow widths. SC 1.4.10 excepts "parts of the
content which require two-dimensional layout for usage or meaning", and a data
table is its canonical case; the scroll is one-dimensional, within the region,
and the page itself never scrolls sideways. The retry action sits under the
Status column it acts on (finding 6's layout change, Stage 5), not in a
far-right column of its own.

## 6. The acknowledgement line, and what jsdom cannot see

The M6 brief names the Ask screen's acknowledgement line as the known case of a
CSS rule hiding an element that the jsdom suite cannot catch. The protection is
now stylesheet-level: `tests/stylesheets.js` parses every rule and
`hidingCauses()` reports any rule matching an element or its ancestors that
hides it (display, visibility, zero size, clip, transparent text, far
offsets). `focusStyles.test.jsx :: the acknowledgement line…` renders the Ask
screen, lands an answer, and asserts the line has no hiding cause and reserves
its height; the same machinery backs the tab-order walk's "nothing reachable is
invisible" and the drop-zone status checks.

## 7. What this pass does not claim

- No automated axe/Lighthouse run: NFR-16's measurement names one, plus a
  manual keyboard walkthrough. The keyboard walkthrough is automated here; the
  axe run belongs with item 8's live pass on the deployed alpha, where the real
  DOM and stylesheets meet, and this item adds no package (the brief's
  condition), so no axe-core here.
- Screen-reader behaviour (NVDA/VoiceOver) is asserted structurally (roles,
  names, live regions), not by listening; the proposal schedules NVDA testing
  under cross-browser verification.
- The dialogue does not mark the page behind it `inert` (noted in Dialog.jsx):
  focus, keyboard and pointer are held, but a screen reader's browse mode can
  still reach behind. An accepted limitation, unchanged by this pass.
- FR-20 / NFR-17 (the visualisation's table equivalent): not built, NIT3004.
