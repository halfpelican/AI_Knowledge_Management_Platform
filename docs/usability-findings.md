# Usability findings — input to Stage 5

Found on 22 September 2026 by working through the Stage 3 ingestion flow by hand:
upload four documents, ingest a transcript, fail an upload deliberately, recover it,
and check the Employee view. None of these are gate failures and none block M6. All
of them are things a person hits in the first ten minutes of using the product.

They belong to **Stage 5 item 4** (accessibility pass) and to whoever picks it up.
Nothing here needs the NPU or a running AI provider — the whole list can be worked on
from any machine with the stack running.

Note how they were found. The suite has 682 tests and every one of these passed
through it untouched, because the front end has no test runner (D-25, audit finding
8, still unsettled across two stages). Every item below came from using the thing.

---

## 1. Dropping a file gives no visible confirmation

**Where** `frontend/src/components/FileDropZone.jsx`, `frontend/src/pages/Upload.jsx:432`

Dropping a file onto the zone works, but nothing near the drop point acknowledges it.
The queue row renders further up the page, outside where attention is when the mouse
is released. The first reaction is that the drop failed.

There *is* an announcement — `role="status" aria-live="polite"` at `Upload.jsx:432` —
but it is `visually-hidden`, so assistive technology is told and sighted users are
not. That is the reverse of the usual failure and worth preserving while fixing.

**Suggested fix** Report state in the drop zone itself: a count ("3 files added"), or
scroll the new row into view. Keep the live region as it is.

> **Closed — 8 November 2026, Stage 5 item 7.** The zone now reports the state
> itself, where the pointer was released: a sentence ("Added 3 files to the
> queue below.", counting any it refused) in a `role="status"` live region that
> is on the screen, not visually hidden, so sighted users and assistive
> technology get the same words (src/components/FileDropZone.jsx `status`;
> src/pages/Upload.jsx `dropStatus`). The page's own hidden live region is kept
> exactly as it was. Test: `tests/dropZone.test.jsx :: says in the zone, on the
> screen and in a live region, what a drop added, and keeps the page live
> region` — which also reads the stylesheets (tests/stylesheets.js), so a CSS
> rule hiding the line fails it, which jsdom alone could not catch.

---

## 2. "No file chosen" reappears immediately after choosing a file

**Where** `frontend/src/components/FileDropZone.jsx`, the input's `onChange`

The component clears `event.target.value` after every change. That is deliberate and
correct — without it, choosing the *same* file twice in a row fires no change event,
so a retry after a failure would silently do nothing. The cost is that the browser's
native label snaps back to "No file chosen", which reads as "that didn't work".

**Suggested fix** Same fix as finding 1. Visually hide the native label and render the
component's own state in its place. One change closes both.

> **Closed — 8 November 2026, Stage 5 item 7.** As suggested: the native input
> is visually hidden and its `<label>` is drawn as the control, so the
> browser's "No file chosen" is gone while the value-clearing retry behaviour
> stays. The zone states the choice itself ("Chosen: minutes.txt" on the
> meeting form; the added-files sentence on Upload). The input keeps the
> keyboard focus, and FileDropZone.css draws the focus ring on the label
> (`.dropzone__input:focus-visible + .dropzone__choose`). Tests:
> `tests/dropZone.test.jsx :: hides the native input, shows its label as the
> control, and states the chosen file itself` and `:: draws the focus ring on
> the label while the hidden input has the keyboard focus`.

---

## 3. The drop target is a thin strip, easy to miss

**Where** `frontend/src/components/FileDropZone.css`, `.dropzone`

The zone is a flex *row* with `var(--space-4)` padding — a horizontal band, not the
large square the pattern usually implies. A drop a little outside it is taken by the
browser, which navigates to the file instead.

**Suggested fix** Give the zone real height, or accept drops on a larger wrapper while
keeping the visual affordance where it is.

> **Closed — 8 November 2026, Stage 5 item 7.** Both halves. The zone is a
> column with `min-height: var(--dropzone-min-height)` (10rem; measured
> 273×206 px at a 320-px viewport), and on the screens that take files the
> whole page is the drop target (`pageDrop`): a drag carrying files anywhere
> over the page lights the zone up, and a drop a little outside it is the
> zone's drop rather than the browser navigating to the file. Drags carrying
> text are left alone. Tests: `tests/dropZone.test.jsx :: is given real height
> by its stylesheet` and `:: takes a file dropped anywhere on the page, lights
> up while one is dragged over it, and leaves other drags alone`.

---

## 4. Drops are silently ignored while an upload is in flight

**Where** `frontend/src/pages/Upload.jsx`, `disabled={busy}` on `FileDropZone`

While the queue is uploading, the drop zone is disabled and `handleDrop` returns
early. Nothing tells the user why their file vanished.

**Suggested fix** Either say so — "Uploading; wait before adding more" — or queue the
dropped files rather than discarding them. The second is better behaviour; the first
is a one-line honest stopgap.

> **Closed — 8 November 2026, Stage 5 item 7.** The first option, said
> properly: while the queue is sending, the zone's status line says why
> nothing can be added, and a drop made meanwhile is answered out loud
> ("Nothing was added, because files are still uploading…") instead of
> vanishing; once the queue finishes, the refusal clears and drops work again.
> Queueing behind a running upload was deliberately not done: the queue sends
> the rows held when Upload was pressed (D-73's hold), so a file queued
> mid-run would sit waiting for a second press nothing on the screen asks
> for. Test: `tests/dropZone.test.jsx :: says why nothing can be added while
> the queue sends, answers a drop with a refusal, and recovers afterwards`.

---

## 5. Attendee selection requires Ctrl+click with no affordance

**Where** `frontend/src/pages/Meetings.jsx`, the attendees control

A native multi-select listbox. Selecting more than one person requires Ctrl+click, and
nothing on screen says so. Clicking the second name deselects the first, so the
natural gesture produces one attendee or none, silently. This was missed by the person
who built the feature, and a meeting was ingested with zero attendees before it was
noticed.

It is also poor for keyboard-only and switch access, where modifier-plus-click is
awkward or impossible.

**Suggested fix** Depends on scale, and the choice should be deliberate:

- **Checkboxes** for a handful of people — no modifier keys, state visible, each
  option individually labelled and announced. Fine up to a dozen.
- **Combobox with an Add button and a removable list** once it is a real
  organisation. A searchable input scales where a list of checkboxes does not.

FR-09 is demonstrated with a few seeded users but describes an organisational
platform. The combobox is the one that survives "what happens with 500 staff?" at the
demonstration.

> **Closed — 8 November 2026, Stage 5 item 7.** The combobox shape, in its
> plainest form: a native single select ("Add an attendee"), an Add button,
> and a visible list with a Remove named for each person
> (src/components/AttendeePicker.jsx). No modifier keys anywhere; the state is
> the list, on the screen; additions and removals are announced politely in
> the same words; a native select finds a name by typing and survives "what
> happens with 500 staff?". A full filtering combobox was considered and set
> aside as custom-widget cost without a current need (CLAUDE.md §9: the boring
> implementation). Tests: `tests/meetingAttendees.test.jsx :: records two
> people chosen one after the other, shows both, and sends both`, `:: gives
> each recorded person their own Remove, named for them, and announces the
> change`, and `:: offers no multiple-selection listbox anywhere on the form`,
> the regression lock against this finding's control coming back.

---

## 6. Check the document repository reflows (not yet a defect)

**Where** `frontend/src/pages/DocumentRepository.jsx`

At roughly half-screen width the repository table scrolls horizontally, putting the
later columns — including the retry action — off screen. At full width it fits, so
this is not a live defect.

It is worth checking against **WCAG 2.1 SC 1.4.10 Reflow**, which asks for content to
work without two-dimensional scrolling down to 320 CSS pixels. Wide tables are the
classic thing that fails it, and the Stage 5 accessibility pass will test at reduced
widths and zoom levels anyway.

**Suggested fix** If it fails, collapse the table to cards below a breakpoint, or move
the action next to the status it belongs to rather than at the far right.

> **Closed — 8 November 2026, Stage 5 item 7 (the check done; one defect found
> and fixed).** Measured in headless Edge at 320 CSS px with the real
> stylesheets: every route now reflows with no page-level sideways scroll; the
> numbers are in docs/accessibility.md §5. The check caught a real SC 1.4.10
> failure first — the page scrolled 70 px under content that painted nothing,
> because the sort heading's visually-hidden span escaped the `.table-scroll`
> clip (no positioned ancestor). Fixed with `position: relative` on
> `.table-scroll` (src/styles/base.css). The table itself still scrolls
> sideways inside its labelled, keyboard-focusable region, which is SC
> 1.4.10's data-table exception, and the retry action already sits under the
> Status column (the Stage 5 layout change this finding suggested). Guards:
> `tests/focusStyles.test.jsx :: anchors .table-scroll so absolutely
> positioned hidden text cannot escape the clip and widen the page`, and the
> tab-order walk keeps the region itself reachable
> (`tests/tabOrder.test.jsx`).

---

## What is already good, and should not be lost while fixing this

> **Checked — 8 November 2026, with the findings closed.** Each item below was
> re-verified:
>
> - the upload queue's hidden live region is untouched and still announces,
>   now beside the visible zone status (`tests/dropZone.test.jsx` asserts
>   both regions);
> - the visibility control's one-choice sentence (D-29) is unchanged
>   (src/pages/Upload.jsx, src/pages/Meetings.jsx);
> - the per-status retry wording (D-32) is unchanged
>   (src/utils/uploadFailure.js, src/utils/documentStatus.js);
> - the token sheet still computes contrast from live values, now from the
>   shared `src/components/contrastPairs.js` list, recomputed from the CSS on
>   disk by `tests/componentSheet.test.jsx`, with the full generated table in
>   docs/accessibility.md.

- The live region on the upload queue (finding 1) — assistive technology is already
  served better than the visual path. Keep it.
- The visibility control degrades to a sentence when the signed-in role has only one
  valid choice, rather than showing a select with one option (D-29).
- The retry wording differs by status: `Indexing failed` says "Please try again",
  `Extraction failed` says what would actually change the outcome (D-32).
- `src/styles/tokens.css` and the component sheet at `/components` compute contrast
  ratios from live token values, which is most of the evidence Stage 5 item 4 needs.
