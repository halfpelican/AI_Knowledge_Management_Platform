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

---

## 2. "No file chosen" reappears immediately after choosing a file

**Where** `frontend/src/components/FileDropZone.jsx`, the input's `onChange`

The component clears `event.target.value` after every change. That is deliberate and
correct — without it, choosing the *same* file twice in a row fires no change event,
so a retry after a failure would silently do nothing. The cost is that the browser's
native label snaps back to "No file chosen", which reads as "that didn't work".

**Suggested fix** Same fix as finding 1. Visually hide the native label and render the
component's own state in its place. One change closes both.

---

## 3. The drop target is a thin strip, easy to miss

**Where** `frontend/src/components/FileDropZone.css`, `.dropzone`

The zone is a flex *row* with `var(--space-4)` padding — a horizontal band, not the
large square the pattern usually implies. A drop a little outside it is taken by the
browser, which navigates to the file instead.

**Suggested fix** Give the zone real height, or accept drops on a larger wrapper while
keeping the visual affordance where it is.

---

## 4. Drops are silently ignored while an upload is in flight

**Where** `frontend/src/pages/Upload.jsx`, `disabled={busy}` on `FileDropZone`

While the queue is uploading, the drop zone is disabled and `handleDrop` returns
early. Nothing tells the user why their file vanished.

**Suggested fix** Either say so — "Uploading; wait before adding more" — or queue the
dropped files rather than discarding them. The second is better behaviour; the first
is a one-line honest stopgap.

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

---

## What is already good, and should not be lost while fixing this

- The live region on the upload queue (finding 1) — assistive technology is already
  served better than the visual path. Keep it.
- The visibility control degrades to a sentence when the signed-in role has only one
  valid choice, rather than showing a select with one option (D-29).
- The retry wording differs by status: `Indexing failed` says "Please try again",
  `Extraction failed` says what would actually change the outcome (D-32).
- `src/styles/tokens.css` and the component sheet at `/components` compute contrast
  ratios from live token values, which is most of the evidence Stage 5 item 4 needs.
