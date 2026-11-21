# Accessibility — the Stage 5 item 7 record

**Date:** 8 November 2026 · **Scope:** the React front end, all M6 screens ·
**Bar:** WCAG 2.1 Level AA, per NFR-16: "The web interface must conform to WCAG
2.1 Level AA, including a minimum 4.5:1 contrast ratio for normal text (SC
1.4.3) and full keyboard operability of all interactive elements (SC 2.1.1)."
NFR-17's accessible table equivalent concerns FR-20's visualisation, which was
NIT3004 scope and not built when this record was written. **It was built on
14 November 2026 (D-132).** Section 8 is its record, sections 1, 3 and 4 carry
its rows, and section 7 says what it still owes in a browser.

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
`frontend/tests/componentSheetTokens.test.jsx` reads the table the sheet renders:
it gives jsdom the values a browser computes for `tokens.css`'s custom properties,
then holds every row to the ratio `tokens.css` gives and to "Pass", never "n/a"
or "Fail", and every token to a swatch or a row on the sheet.

### Text (SC 1.4.3, AA 4.5:1)

| Foreground | Background | Ratio | Requires | Result | Where |
|---|---|---|---|---|---|
| `--color-text` #1f2933 | `--color-surface` #ffffff | 14.76:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-surface-alt` #f3f4f6 | 13.41:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-danger-surface` #fef3f2 | 13.57:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-success-surface` #ecfdf3 | 13.99:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-warning-surface` #fffaeb | 14.14:1 | 4.5:1 | Pass | body text everywhere a notice can put it |
| `--color-text` #1f2933 | `--color-background` #ffffff | 14.76:1 | 4.5:1 | Pass | body text everywhere a notice can put it (PR #119’s surfaces) |
| `--color-text` #1f2933 | `--color-info-surface` #eff6ff | 13.56:1 | 4.5:1 | Pass | body text everywhere a notice can put it (PR #119’s surfaces) |
| `--color-text` #1f2933 | `--color-status-indexed-surface` #dcfce7 | 13.43:1 | 4.5:1 | Pass | body text everywhere a notice can put it (PR #119’s surfaces) |
| `--color-text` #1f2933 | `--color-status-not-indexed-surface` #fef3c7 | 13.25:1 | 4.5:1 | Pass | body text everywhere a notice can put it (PR #119’s surfaces) |
| `--color-text` #1f2933 | `--color-role-employee-surface` #dbeafe | 12.09:1 | 4.5:1 | Pass | held on every surface the sweep knows; this one is the Profile page’s Employee role badge, which carries only its own text (FEA-7) |
| `--color-text-muted` #4b5563 | `--color-surface` #ffffff | 7.56:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-surface-alt` #f3f4f6 | 6.87:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-danger-surface` #fef3f2 | 6.95:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-success-surface` #ecfdf3 | 7.17:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-warning-surface` #fffaeb | 7.24:1 | 4.5:1 | Pass | hints, metadata, empty states |
| `--color-text-muted` #4b5563 | `--color-background` #ffffff | 7.56:1 | 4.5:1 | Pass | hints, metadata, empty states (PR #119’s surfaces) |
| `--color-text-muted` #4b5563 | `--color-info-surface` #eff6ff | 6.94:1 | 4.5:1 | Pass | hints, metadata, empty states (PR #119’s surfaces) |
| `--color-text-muted` #4b5563 | `--color-status-indexed-surface` #dcfce7 | 6.88:1 | 4.5:1 | Pass | hints, metadata, empty states (PR #119’s surfaces) |
| `--color-text-muted` #4b5563 | `--color-status-not-indexed-surface` #fef3c7 | 6.79:1 | 4.5:1 | Pass | hints, metadata, empty states (PR #119’s surfaces) |
| `--color-text-muted` #4b5563 | `--color-role-employee-surface` #dbeafe | 6.19:1 | 4.5:1 | Pass | held on every surface the sweep knows; this one is the Profile page’s Employee role badge (FEA-7) |
| `--color-primary` #1d4ed8 | `--color-surface` #ffffff | 6.70:1 | 4.5:1 | Pass | links; the in-page 403’s link sits on the error notice |
| `--color-primary` #1d4ed8 | `--color-surface-alt` #f3f4f6 | 6.09:1 | 4.5:1 | Pass | links; the in-page 403’s link sits on the error notice |
| `--color-primary` #1d4ed8 | `--color-danger-surface` #fef3f2 | 6.16:1 | 4.5:1 | Pass | links; the in-page 403’s link sits on the error notice |
| `--color-primary` #1d4ed8 | `--color-info-surface` #eff6ff | 6.16:1 | 4.5:1 | Pass | a link in an info notice, which sits on PR #119’s info fill: the knowledge map’s empty selection, in both its views |
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
| `--color-heading` #1f2933 | `--color-background` #ffffff | 14.76:1 | 4.5:1 | Pass | the landing page’s heading and feature titles (PR #119) |
| `--color-heading` #1f2933 | `--color-surface` #ffffff | 14.76:1 | 4.5:1 | Pass | a title in a plain table cell, as in the knowledge map’s target columns (PR #119); a row-header title, as in the document table, takes `.data-table th`’s `--color-text-muted` on `--color-surface-alt` instead, 6.87:1 above |
| `--color-link` #1d4ed8 | `--color-background` #ffffff | 6.70:1 | 4.5:1 | Pass | the sign-in card’s “Forgot password” link (PR #119) |
| `--color-link` #1d4ed8 | `--color-surface` #ffffff | 6.70:1 | 4.5:1 | Pass | the dashboard panels’ links on hover (PR #119) |
| `--color-primary-hover` #1e40af | `--color-info-surface` #eff6ff | 8.01:1 | 4.5:1 | Pass | every info notice’s text: PR #119’s rule in `Repository.css` comes after `Notice.css`’s in the build, so it reaches every screen |
| `--color-danger-text` #991b1b | `--color-danger-surface` #fef3f2 | 7.64:1 | 4.5:1 | Pass | every error notice’s text, by the same rule (PR #119); the title keeps `--color-danger` |
| `--color-status-indexed` #166534 | `--color-status-indexed-surface` #dcfce7 | 6.49:1 | 4.5:1 | Pass | the document table’s “Indexed” badge (FR-15, PR #119), and the Profile page’s Administrator role badge, #119’s own colours (FEA-7) |
| `--color-status-not-indexed` #92400e | `--color-status-not-indexed-surface` #fef3c7 | 6.37:1 | 4.5:1 | Pass | the badge for every other status (FR-15, PR #119) |
| `--color-primary-hover` #1e40af | `--color-role-employee-surface` #dbeafe | 7.15:1 | 4.5:1 | Pass | the Profile page’s Employee role badge, #119’s own colours (FEA-7) |
| `--color-illustration-bubble-text` #e5e7eb | `--color-text-muted` #4b5563 | 6.10:1 | 4.5:1 | Pass | the landing illustration’s left chat bubble (PR #119) |

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
| `--color-text-muted` #4b5563 | `--color-surface` #ffffff | 7.56:1 | 3:1 | Pass | the knowledge map’s contributor shape (FR-20, D-132) |
| `--color-text` #1f2933 | `--color-surface` #ffffff | 14.76:1 | 3:1 | Pass | the knowledge map’s selected node: its outline and its lines (FR-20, D-132) |
| `--color-border-strong` #667085 | `--color-background` #ffffff | 4.97:1 | 3:1 | Pass | the landing page’s outline button (PR #119) |
| `--color-illustration-device` #111827 | `--color-background` #ffffff | 17.74:1 | 3:1 | Pass | the landing illustration’s device and figure, on the page (PR #119) |
| `--color-illustration-figure` #544ce6 | `--color-illustration-device` #111827 | 3.00:1 | 3:1 | Pass | the figure’s body on the figure’s circle (PR #119) |
| `--color-accent` #1d4ed8 | `--color-background` #ffffff | 6.70:1 | 3:1 | Pass | the token behind one of the illustration’s shapes, drawn at 12% opacity (PR #119) |

FR-20's knowledge map also uses four pairs already in this table, each against
`--color-surface`, which is what the diagram, its legend and its Selected panel
sit on: `--color-primary` (6.70:1) fills the document shape, `--color-success`
(5.69:1) the meeting shape, `--color-warning` (7.52:1) the tag shape, and
`--color-border-strong` (4.97:1) draws the lines and each node's outline.
Section 8 names the tests that hold the four fills to four different tokens.

**PR #119's redesign (17 November 2026).** Its rows are the ones marked PR #119
in both tables: 21 cases in `contrast.test.js`, recomputed for this table from
`tokens.css`. Two notes go with them.

- **Four of the home page illustration's colours changed.** The illustration
  is `aria-hidden` decoration, and SC 1.4.11 asks no contrast of it. But
  `contrast.test.js` accounts for every colour token a stylesheet uses by a
  pair or an exemption, and none was exempted:
  - the screen, #0b0c10, 1.10:1 against the device, is now the device's
    #111827, so the bezel between them is gone;
  - the figure's body, #4f46e5, 2.82:1 on the figure, is now #544ce6, 3.00:1;
  - the keyboard, #1f2937, is now `--color-text`, #1f2933, which looks the
    same, and still measures 1.20:1 against the device, which no pair checks;
  - the left chat bubble, #374151, is now the lighter `--color-text-muted`,
    on which its text measures 6.10:1 (8.33:1 before).

  Only the first two fixed a failing pair; the last two are existing tokens in
  place of new ones. Exempting the illustration's colours instead would
  restore all four.
- **The info and error notices have lost their leading edge.** PR #119's
  `.notice--info` and `.notice--error` in `Repository.css` come after
  `Notice.css`'s in the build, so on every screen they draw a 1px
  `--color-border` all round in place of the 4px edge. While they stand, the
  notice edges the `--color-primary` and `--color-danger` rows above name are
  not drawn. A notice is not a control and says what it is in words, so no AA
  criterion depends on the edge.

**The Profile page's role badge (FEA-7, 18 November 2026)** is back in #119's
colours. The Administrator's uses the “Indexed” pair; the Employee's adds one
token, `--color-role-employee-surface`, and its three rows above (three cases in
`contrast.test.js`). #119's borders, a shade darker than each fill (#bbf7d0 and
#bfdbfe, about 1.1:1 against it), have no token, so each border is drawn in its
own fill. A badge is not a control, and its text names the role.

### Documented exceptions

| Colour | Why no pair is required | Held by |
|---|---|---|
| `--color-border` #d0d5dd (1.47:1 on surface) | Decorative separators: table-row rules, panel outlines, the heading underline. Never the sole boundary of a control — `contrast.test.js :: never makes the decorative border the boundary of a control` fails any rule that puts it on one. The one control that had it, the Ask screen's conversation-list item, was moved to `--color-border-strong` in this pass | `tests/contrast.test.js` |
| `--color-overlay` (the modal scrim) | Decorative and `aria-hidden`; nothing is read through it. The dialogue restates its own surface and text colour, which the test asserts, because white text on the bare composite would measure about 4.05:1 | `contrast.test.js :: the modal scrim backs no text` |
| The password strength meter's fills | The bar is `aria-hidden` decoration; its text equivalent is the visible "Password strength: …" sentence (SC 1.1.1) | `tests/textEquivalents.test.jsx` |
| The button spinner (`currentColor`) | `aria-hidden` decoration; the label changes with it | `tests/textEquivalents.test.jsx` |
| `--shadow-sm`, `--shadow-md`, `--shadow-lg` (PR #119; `--color-text`’s rgb 31 41 51 at 6–14% alpha, inside the token) | Decorative depth, never a boundary anything depends on. Of their eleven uses, eight are on elements with a border of their own (the dashboard’s panels and filter box, the profile card and form, the repository’s filter and browse boxes, every table’s scroll region), one is the hover of the home page’s “Sign in” link, whose fill is its boundary (since 18 November 2026 #119’s button rules reach only the home page’s two calls to action, so no other primary button has it), and two are on the `aria-hidden` illustration, whose white icon tiles stand out from the page by their shadow alone | No test holds this. `contrast.test.js`’s sweep follows `var(--shadow-sm)` into the token and finds a colour literal, not a `--color-` token, so it never sees the colour; `stylesheets.test.js :: keeps every colour literal in tokens.css` keeps that literal in the one file. The eleven uses were checked by hand on 17 November 2026 |

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
sign-in, the home page and the two account-recovery pages to a visitor not
signed in (the forgotten-password page before and after it is sent, the reset
page with its link and with a link that does not work), then the dashboard,
documents, upload, meetings, the Profile page and ask, end to end, and asserts,
on every screen:

- the skip link is the first stop, hidden until focused and shown the moment it
  is (`focusStyles.test.jsx` holds the hiding to the `:not(:focus)` rule);
- no positive `tabindex` anywhere — the DOM order is the tab order, which is
  what lets the Ask screen's two-column layout collapse to one column without
  reordering (the aside is after the main column in the DOM);
- nothing reachable is invisible while it holds focus, checked against the
  stylesheets through `tests/stylesheets.js`. The one stop allowed to be hidden
  is a file input whose label shows its focus ring, as the drop zone's does;
  until 18 November 2026 any field with a visible label was let through;
- no trap: the walk fails if focus revisits a stop before leaving the page, and
  the delete confirmation's Tab cycle is tested inside the dialogue both ways;
- the table region that scrolls at narrow widths is itself a stop
  (`tabIndex=0`, `role="region"`, named), ahead of the rows inside it, so the
  sideways scroll is keyboard-operable.

Since 14 November 2026 the same file walks the knowledge map, as an Employee
and as an Administrator, with the same four assertions (D-132; section 8 gives
its order).

## 4. Text equivalents (SC 1.1.1)

The interface has no canvas charts. Its raster images are D-137's profile
pictures, drawn by `components/Avatar.jsx` wherever people are listed: the
header, role management, the attendee lists and the Profile page. Each is
decoration, because the person's name is always beside it: the picture's `alt`
is empty, and the initials shown in its place are `aria-hidden` and painted by
the stylesheet, so nothing is read twice (`frontend/tests/avatars.test.jsx`,
`frontend/tests/profileCard.test.jsx`). The Profile page's preview of a picture
chosen but not yet sent is named "Preview"; no test holds that name. It has one
graphic, FR-20's node-link diagram, which is drawn as SVG and has a text
equivalent of its own (the three knowledge map rows below, and section 8). Its
other non-text content is bars, glyphs and markers. Each carries its information
as text
(`frontend/tests/textEquivalents.test.jsx`, except where a row names another
file):

| Non-text content | Text equivalent |
|---|---|
| Upload progress bar | `role="progressbar"` named for its file, `aria-valuenow` and `aria-valuetext`, the visible percentage beside the track; an indeterminate bar carries no value — zero would read as "no progress" — and says what it is doing |
| Browse facet count | The button's name is "Finance 3 documents": the bare number is `aria-hidden`, the counted noun visually hidden |
| Sort direction arrow | ", sorted ascending/descending" in the button's name; `aria-sort` on the column; the arrow is `aria-hidden` |
| Citation marker [1] | Accessible name "Source for statement 1"; the bracket is `aria-hidden` |
| Button spinner | `aria-busy`, spinner `aria-hidden`, and the label changes ("Signing in…") |
| Password strength meter | The visible "Password strength: …" sentence; each rule carries a hidden "Met:"/"Not met:" prefix so state is never colour alone (SC 1.4.1) |
| Dashboard totals | Figures are `<dd>` values whose `<dt>` labels sit beside them in the same definition list |
| Knowledge map: a node's shape and colour (FR-20) | The node is a link whose name begins with its type in a word ("Document: Leave policy, 3 connections shown"); the shape is an `aria-hidden` SVG. The Items table has a Type column in words, and the legend puts each shape beside its word |
| Knowledge map: the lines (FR-20) | The Relationships table: one row per line, read "from, relationship, to" in words. The lines' SVG layer is `aria-hidden` and holds nothing focusable and no text |
| Knowledge map: the selected node's heavier outline and lines | `aria-current`, the visible word "Selected", and what a second selection does, in the node's name; the Selected panel lists its connections as links |
| A profile picture, or the initials in its place (D-137) | The person's name, always beside it. The picture's `alt` is empty and the initials are `aria-hidden`, painted from `data-initials` by `Avatar.css` (`avatars.test.jsx`) |
| The home page's illustration and its feature glyphs (PR #119) | Decoration, `aria-hidden` as a whole: each feature's words say what its glyph shows, and the lead says what the illustration does. Nothing in it is focusable (`dashboard.test.jsx :: hides the illustration and every glyph from assistive technology…`) |

The sweep in the same file asserts no `aria-hidden` subtree contains a
focusable element, and the tab-order walk cannot visit one (an `aria-hidden`
ancestor is a hiding cause).

**Motion (SC 2.2.2, Pause, Stop, Hide).** The home page's illustration is the
one thing that moves on its own beside the page's content. Its cursor blinks
four times, 4 seconds, and holds still; each of its three icons floats once,
the last coming to rest 4.2 seconds after the page opens. So every animation
ends within five seconds, and none needs a control to stop it. A visitor whose
system asks for reduced motion sees none of it: `Home.css` sets
`animation: none` on both under `prefers-reduced-motion: reduce`, rather than
relying on `base.css`'s rule, which shortens an animation but does not cap its
count. `frontend/tests/homeMotion.test.jsx :: SC 2.2.2: the home page’s motion
stops on its own, and not at all for a visitor who asks for less` holds both
from the stylesheets, delays counted. The loading indicators, the button's
spinner and the indeterminate progress bar, are not counted here: they run only
while work is in flight, which is the case SC 2.2.2's exception for essential
motion is about. Under reduced motion, `base.css`'s rule shortens their
animation but does not cap its count, so they are not still; that is a known
low, not fixed here.

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

**`/knowledge-map` is not in the table above: it has not been measured.** It
was built on 14 November 2026 (D-132), after this measurement, and nothing in
the suite measures a width. What the stylesheet is written to do is in
section 8; whether it does it at 320 px is owed in a browser (section 7).

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
- FR-20 / NFR-17 (the knowledge map and its table view), built on 14 November
  2026 (D-132), is asserted structurally only. Three things are owed in a
  browser, by a person, and none is claimed here:
  - **Reflow at 320 CSS px** (SC 1.4.10) for `/knowledge-map`, measured as
    section 5 measured the other routes: that the page itself does not scroll
    sideways, that the diagram scrolls inside its own region, and that the
    legend, the diagram and the Selected panel stack in one column. Also that a
    long title wraps inside its node and is not clipped, at 200% text size as
    well, and that each line meets the edge of its node.
  - **The axe (or Lighthouse) run** NFR-16's measurement names, for
    `/knowledge-map`, with the rest of the deployed alpha.
  - **NFR-17's own test**: "Screen-reader test (NVDA/Voiceover) confirming all
    node and relationship information is reachable through the tabular view".
    The suite asserts the tables' structure, names and sorting; nobody has
    listened to it.

## 8. The knowledge map (FR-20, NFR-17; D-132, 14 November 2026)

`/knowledge-map` is a legend, a node-link diagram, a Selected panel and, under
them, a table view of the same nodes and relationships. Every claim below names
the test that holds it. `knowledgeMap.test.jsx` runs each of its cases as an
Employee and as an Administrator.

**Node colours and shapes (SC 1.4.1, SC 1.4.11).** FR-20: "node type
distinguished by colour and shape".

| Type | Shape | Fill | On `--color-surface` |
|---|---|---|---|
| Document | square (`rect`) | `--color-primary` #1d4ed8 | 6.70:1 |
| Meeting | circle (`circle`) | `--color-success` #067647 | 5.69:1 |
| Tag | diamond (`polygon`) | `--color-warning` #93370d | 7.52:1 |
| Contributor | triangle (`polygon`, other points) | `--color-text-muted` #4b5563 | 7.56:1 |

- Each fill is one token, the four differ, and each is a tested 3:1 pair on the
  surface: `contrast.test.js :: gives each of the four node classes one fill
  token, four different ones, each a tested 3:1 pair on the surface`, with the
  ratios themselves under `SC 1.4.11: component boundaries and fills meet 3:1`.
- The rendered shapes are four different elements or outlines, each carries its
  type's class, the stylesheet rules that match them give four different fills,
  and the legend shows the same four: `knowledgeMap.test.jsx :: draws each of
  the four types as a different shape with its own class, names its type in a
  word, and lists the same four in the legend` and `:: gives the four shapes
  four different fills in the stylesheets, each from one colour token`.
- Lines are `--color-border-strong` (4.97:1), never the decorative
  `--color-border` (1.47:1); the selected node's lines are `--color-text`
  (14.76:1) and heavier: `contrast.test.js :: draws the lines in a tested 3:1
  colour, never the decorative border, and the selected node’s in another`, and
  `knowledgeMap.test.jsx :: draws the selected node’s lines heavier, by class,
  and after the others`.
- No colour is an SVG attribute or an inline style, so the two sweeps over the
  stylesheets see every one: `textEquivalents.test.jsx :: sets no colour as an
  SVG attribute or an inline style: every colour is a class the contrast sweep
  reads`. Inline style is grid position only.
- Labels and counts are text on the surface, never on a fill, so the text pairs
  in section 1 are the ones that apply. This is how the page is written
  (`src/pages/KnowledgeMap.jsx`: no text inside any SVG, which
  `textEquivalents.test.jsx :: hides every SVG from assistive technology…`
  asserts).
- Not measured: one node colour against another. The type never depends on
  telling two fills apart, because the shape and the word are always there.

**The diagram's text equivalent (SC 1.1.1, NFR-17).**

- Every SVG on the page (the lines' layer, each node's shape, the legend's
  shapes and its sample line) is `aria-hidden`, holds nothing focusable and
  holds no text: `textEquivalents.test.jsx :: hides every SVG from assistive
  technology, with nothing focusable and no text inside, and names each node in
  words`. The diagram is also in that file's sweep, `:: keeps every aria-hidden
  subtree free of focusable elements`.
- The two tables hold exactly the nodes and edges the diagram draws, an
  unconnected node included, and a tag reads with its dimension:
  `knowledgeMap.test.jsx :: holds exactly the served nodes and edges in the two
  tables and on the diagram, the unconnected meeting included` and `:: reads a
  tag with its dimension everywhere…`.
- Every column of both tables sorts ascending and descending from a native
  button in a `th` that carries `aria-sort`, reached by Tab:
  `knowledgeMap.test.jsx :: sorts the Items table by …` (three columns) and
  `:: sorts the Relationships table by …` (three columns). jsdom does not turn
  Enter or Space into a click, so the tests reach the button with Tab and click
  it; that a native button answers both keys is the browser's.
- Selecting from a row does what selecting a node does: `knowledgeMap.test.jsx
  :: selecting the document from …` (the node, its Items row, a Relationships
  row).
- When a view is partial, the sentence that says so comes before the "Skip to
  the table view" link and is each table's accessible description:
  `knowledgeMap.test.jsx :: … says so before the skip link, worded from the
  reply’s own maximum, and as each table’s description`.

**Tab order (SC 2.1.1, SC 2.4.3).** `tabOrder.test.jsx :: FR-20 / NFR-17: the
knowledge map, its diagram and its table view (D-132)`, as each role, with the
walk's shared assertions (the skip link first, no positive `tabindex`, no stop
hidden by markup or by any stylesheet rule, no trap):

1. the header's stops, as on every screen;
2. "Skip to the table view", which puts focus on the table view's heading
   (`knowledgeMap.test.jsx :: "Skip to the table view" is a link ahead of the
   diagram that lands on the table view`);
3. the diagram's scroll region, then one stop per node, **column by column, top
   to bottom**: contributors, then documents and meetings, then tags. The
   diagram adds one stop for its region and one per node. The server's order is
   walk order, which would move between columns on every source, so the nodes
   are rendered in the layout's order instead;
4. the Selected panel's links: the selected node's connections, the open
   action, "Show the whole map";
5. the Items region, its three sort buttons, then a link per row; the
   Relationships region, its three sort buttons, then two links per row.

A selected contributor is plain text, not a link, so it is not a stop:
`tabOrder.test.jsx :: a selected contributor is not a stop on the diagram…`.
Every interactive element is a native link or button; there is no key handler
and no `role="button"` on the page. After a selection made on the page has
loaded, focus is moved to the Selected panel's heading: `knowledgeMap.test.jsx
:: moves focus to the Selected panel’s heading once a selection made on the
page has loaded`.

**Reflow (SC 1.4.10): written for, not measured.** The diagram sits in a
labelled, focusable scroll region with a minimum width
(`--layout-map-min-width`), as a data table does, so a narrow screen scrolls
the diagram inside its region and not the page; the legend, the diagram and the
panel stack in one column at or below 64rem, in their DOM order; a long label
wraps (`overflow-wrap: anywhere`) and makes the rows taller. The suite asserts
the region's role, name and `tabindex` and the arithmetic of the layout
(`knowledgeMap.test.jsx :: puts each node in its type’s column…`). It measures
no width. Section 7 lists the measurement as owed.

**The component sheet** shows the legend and a sample diagram from sample data
and requests nothing: `componentSheet.test.jsx :: shows the knowledge map’s
legend with its four types and a sample map with a node of each, from sample
data, asking the API for nothing`. The node-colour pairs are in its Contrast
table (`src/components/contrastPairs.js`).

## 9. The knowledge map's second view (D-138, 16 November 2026)

The same page's second view, at `/knowledge-map?view=evidence`: claims joined to the passages
they cite. It is asserted structurally, as section 8's view is, and the same three browser
measurements are owed for it (the end of this section).

**Reaching it (SC 2.4.3).** A link styled as a button, "Show claims and passages", is the next
link and the next tab stop after "Skip to the table view". In the second view the same place
holds "Show documents, meetings, tags and contributors". After a switch, focus is on the page's
heading. `knowledgeMap.test.jsx`, under "the switch between the two views", as each role.

**Type by colour and shape, and never by colour alone (SC 1.4.1, SC 1.4.11).**

| Type | Shape | Fill | On `--color-surface` | Also in words |
|---|---|---|---|---|
| Claim | square (`rect`) | `--color-text` #1f2933 | 14.76:1 | "Claim" in the legend, the node's name and the Type column |
| Passage | circle | `--color-primary` | 6.70:1 | "Passage", in the same three places |

Both pairs were already in section 1's table. `contrast.test.js :: the second view (D-138): gives
the claim and the passage one fill token each, two different ones, each a tested 3:1 pair on the
surface`.

**What a line's weight says is also said in a number (SC 1.4.1).** A heavier line means the
pairing was admitted more often: three widths, for 1, for 2 to 4, and for 5 or more. The lines
are in an `aria-hidden` layer. The same number is the Relationships table's "Times admitted"
column, one row per line. `contrast.test.js :: the second view (D-138): a line’s three weights
are three widths, each greater than the last, and no colour of their own`.

**The selected item** has a heavier outline, darker lines, `aria-current` and the visible word
"Selected". Its lines keep their weight, so the legend says "darker lines" for this view.
A selected item's lines therefore differ from the others by colour alone, and the two strokes
are 2.97:1 against each other, under 3:1. What those lines say is also in text: the pane lists
what the selected item is joined to ("Supported by" or "Cited by"), and the Relationships
table has a row for each line. The first view's selected lines are heavier as well as darker.

**AI-generated content says so in words (NFR-15).** A passage of a meeting's AI-written summary
carries the app's "Suggested by AI" mark wherever its label is shown: its node, its Items row,
the To cells and the Claim review's list. A dashed outline is a second cue and never the only
one. `knowledgeMap.test.jsx`, under "NFR-15: a passage that is AI-generated content says so in
words".

**The table equivalent (NFR-17, SC 1.1.1, SC 1.3.1).** Two tables, as section 8's view has:
Items (Name, Type, Connections shown) and Relationships (From, Relationship, To, Times admitted).
Every column heading is a button that sorts, with `aria-sort`, and "Times admitted" sorts as a
number. Each row's ends are the same links as the nodes, so a row selects as a node does.
`knowledgeMap.test.jsx`, under "NFR-17: the table view holds the same claims, passages and
citations as rows".

**The Claim review pane.** A selected claim is plain text, not a link, and the pane says "A
claim has no page of its own, so there is nothing to open." After a selection made on the page
has loaded, focus is on the pane's heading. A selected passage links to its source's page.

**Tab order.** `tabOrder.test.jsx`, under "its second view, claims and passages (D-138)": the
view's whole walk as each role, with no stop hidden by a stylesheet rule, the switch straight
after the skip link, claims before passages, and a selected claim not a stop.

**Owed in a browser, by a person,** as for section 8's view: a screen-reader run (NVDA or
VoiceOver) through both tables; reflow at 320 CSS pixels; an axe run; and that the two shapes,
the three line widths and the switch beside the skip link paint as the stylesheet says.

## 10. A document's summary and key points (FR-10; D-139, 21 November 2026)

FR-10's summary of a document and its key points are one block, drawn by one component
(`components/DocumentSummary.jsx`) in two places: beneath the title of a search result, above its
snippet, and beneath the title of the document page, above its metadata, classification and
text. Every claim below names the test that holds it. `search.test.jsx` renders the search
screen and `documentSummary.test.jsx` the document page.

**AI-generated content says so in words (NFR-15, SC 1.4.1).** The block opens with the app's
"Suggested by AI" mark and the sentence "This is a summary of the document, not its own text.",
ahead of the summary they are about. The dashed boundary is the second cue, never the only one,
and it is `ai-content`'s: no rule that matches the block draws another border. The snippet under
it in a search result, and the extracted text on the document page, are the document's own words
and are outside the boundary. `search.test.jsx :: marks the summary and its key points as AI
content…`; `documentSummary.test.jsx :: marks them as AI content…` and `:: draws them where a
reader can see them…`, which also holds that no stylesheet rule hides the mark, the summary, the
sentence below or a key point. `documentSummary.test.jsx :: marks them as AI content…` holds the
sentence beside the mark to its words as written here, as it holds the mark's, so a sentence
emptied or reworded fails it.

**Contrast.** No new colour and no new pair. The mark, the sentence beside it, the sentence about
a summary cut short and the line for a document with no summary are `--color-text-muted` on the
page (7.56:1); the summary and the key points are body text (14.76:1); the boundary is
`--color-border-strong` (4.97:1). `contrast.test.js`'s sweep reads `DocumentSummary.css` with
every other stylesheet.

**The key points are a list (SC 1.3.1).** A `ul` of `li`, named "Key points" by the visible
words above it. A summary that came with no key points has no list, and a key point that says
nothing is left out. The block has no heading of its own: a search page would gain one for each
result. `:: renders five key points as five list items, in the order they were sent` in both
files; `search.test.jsx :: shows a summary that came with … without an empty list`.

**A summary of part of a long document says so**, in a sentence inside the block: "This summary
covers only the first part of the document." (FR-10: never "summarised from a fragment without
the user being told"). `:: says so when summary_truncated is true` in both files. In a search
result, `search.test.jsx :: draws a summary cut short where a reader can see it…` holds that no
stylesheet rule hides that sentence, the key points' name or a key point, the result's own rules
included.

**No summary.** A search result with none shows nothing in its place, and is the result it was
before summaries existed. The document page says "No summary has been generated for this
document." in one line, which is the page's own sentence and carries no mark. `search.test.jsx
:: renders a result with … as it always has`; `documentSummary.test.jsx :: shows the line, and
no summary block, mark or list, when …`, which also holds that no stylesheet rule hides the line.
A summary of only white space is no summary, on both screens: a case of each of those tests.

**Tab order (SC 2.1.1).** The block holds no control and is not focusable itself, so it adds no
tab stop to either screen. Both "marks … as AI content" tests assert that nothing in the block,
itself included, can take focus. `tabOrder.test.jsx` does not walk a search page with results or
the document page, so those two assertions are what holds this.

**Text only.** The summary and key points are the model's words about a file anyone may have
uploaded. They are rendered as text, never as HTML. `search.test.jsx :: renders a summary and a
key point holding markup as the characters they are`.

**Reflow (SC 1.4.10), measured for the block and not for the pages.** In headless Edge 158 on
21 November 2026: the block's markup as each screen renders it, with the built stylesheet,
inside a 320-CSS-px iframe. The summary was 600 characters and each of five key points 200,
each holding a 135-character string with nowhere to break. `documentElement.clientWidth` and
`scrollWidth` were both 305, and each block's own were both 271, so nothing scrolled sideways.
The boundary computed as 1px dashed in both places and the bullet as a disc in both. With the
summary's `word-break` switched off the same page was 1102 wide, and with the key points'
switched off, 1126, so those two rules are what holds it. `documentSummary.test.jsx :: lets a
long unbroken string in the summary or a key point wrap inside the block…` holds both rules
from the stylesheet. This was a static page, not the running application: no header, no router
and no API.

**The component sheet** shows the block cut short, the line for no summary, and a search result
carrying a summary. `componentSheet.test.jsx :: shows FR-10’s document summary in its states…`.

**Owed in a browser, by a person:** the search page and the document page themselves at 320 CSS
pixels, with real summaries; a screen-reader run (NVDA or VoiceOver) through a result and the
document page, to hear the mark before the summary and the list announced by its name; and an
axe run, with the rest of the deployed alpha.
