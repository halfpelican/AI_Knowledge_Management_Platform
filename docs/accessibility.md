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
| `--color-text-muted` #4b5563 | `--color-surface` #ffffff | 7.56:1 | 3:1 | Pass | the knowledge map’s contributor shape (FR-20, D-132) |
| `--color-text` #1f2933 | `--color-surface` #ffffff | 14.76:1 | 3:1 | Pass | the knowledge map’s selected node: its outline and its lines (FR-20, D-132) |

FR-20's knowledge map also uses four pairs already in this table, each against
`--color-surface`, which is what the diagram, its legend and its Selected panel
sit on: `--color-primary` (6.70:1) fills the document shape, `--color-success`
(5.69:1) the meeting shape, `--color-warning` (7.52:1) the tag shape, and
`--color-border-strong` (4.97:1) draws the lines and each node's outline.
Section 8 names the tests that hold the four fills to four different tokens.

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

Since 14 November 2026 the same file walks the knowledge map, as an Employee
and as an Administrator, with the same four assertions (D-132; section 8 gives
its order).

## 4. Text equivalents (SC 1.1.1)

The interface has no raster images and no canvas charts. It has one graphic,
FR-20's node-link diagram, which is drawn as SVG and has a text equivalent of
its own (the last three rows below, and section 8). Its other non-text content
is bars, glyphs and markers. Each carries its information as text
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
| Knowledge map: a node's shape and colour (FR-20) | The node is a link whose name begins with its type in a word ("Document: Leave policy, 3 connections shown"); the shape is an `aria-hidden` SVG. The Items table has a Type column in words, and the legend puts each shape beside its word |
| Knowledge map: the lines (FR-20) | The Relationships table: one row per line, read "from, relationship, to" in words. The lines' SVG layer is `aria-hidden` and holds nothing focusable and no text |
| Knowledge map: the selected node's heavier outline and lines | `aria-current`, the visible word "Selected", and what a second selection does, in the node's name; the Selected panel lists its connections as links |

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

Both pairs were already in section 3's table. `contrast.test.js :: the second view (D-138): gives
the claim and the passage one fill token each, two different ones, each a tested 3:1 pair on the
surface`.

**What a line's weight says is also said in a number (SC 1.4.1).** A heavier line means the
pairing was admitted more often: three widths, for 1, for 2 to 4, and for 5 or more. The lines
are in an `aria-hidden` layer. The same number is the Relationships table's "Times admitted"
column, one row per line. `contrast.test.js :: the second view (D-138): a line’s three weights
are three widths, each greater than the last, and no colour of their own`.

**The selected item** has a heavier outline, darker lines, `aria-current` and the visible word
"Selected". Its lines keep their weight, so the legend says "darker lines" for this view.

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
