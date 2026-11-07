import { useId, useState } from 'react'
import { messageForStatus } from '../api/client.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { SOURCE_TYPE, TEXT } from '../constants.js'
import { contrastRatio } from '../utils/contrast.js'
import { FILE_INPUT_ACCEPT } from '../utils/uploads.js'
import { AnswerBody, PartialMatches, SourcesPanel } from './Answer.jsx'
import { ActiveFilterList, FacetGroup, SortHeader } from './Browse.jsx'
import Button from './Button.jsx'
import DashboardPanel from './DashboardPanel.jsx'
import Dialog from './Dialog.jsx'
import FileDropZone from './FileDropZone.jsx'
import NotPermitted from './NotPermitted.jsx'
import Notice from './Notice.jsx'
import PasswordInput from './PasswordInput.jsx'
import PasswordRequirements from './PasswordRequirements.jsx'
import ProgressBar from './ProgressBar.jsx'
import SearchField from './SearchField.jsx'
import { SearchResultGroup } from './SearchResults.jsx'
import SelectInput from './SelectInput.jsx'
import TextAreaInput from './TextAreaInput.jsx'
import TextInput from './TextInput.jsx'
import './ComponentSheet.css'
// The upload queue's status styles, for the limited row shown under "Limits (D-79)".
import '../pages/Upload.css'

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
  '--color-overlay',
]

const SPACING_TOKENS = ['--space-1', '--space-2', '--space-3', '--space-4', '--space-5', '--space-6', '--space-7']

const FONT_TOKENS = ['--font-sans', '--font-mono']

const TYPE_TOKENS = ['--text-sm', '--text-base', '--text-lg', '--text-xl', '--text-2xl']

const RADIUS_TOKENS = ['--radius-sm', '--radius-md', '--radius-full']

const FOCUS_TOKENS = ['--color-focus', '--focus-ring-width', '--focus-ring-offset']

const LAYER_TOKENS = ['--z-skip-link', '--z-dialog', '--duration-spinner']

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
  // FR-15's browse values sit in a panel on the alt surface.
  { label: 'Control border on alt surface (non-text)', fg: '--color-border-strong', bg: '--color-surface-alt', minimum: 3 },
  { label: 'Focus ring on surface (non-text)', fg: '--color-focus', bg: '--color-surface', minimum: 3 },
]

/* Components for the M6 screens, in build order. Named here so the sheet stays the index of the design system. */
const BUILT = [
  { name: 'Register, sign in, log out (FR-01, FR-02, FR-04)', paths: ['/register', '/login'] },
  { name: 'Role management (FR-05, Administrator only)', paths: ['/admin/roles'] },
  { name: 'Access Denied (FR-06, where a guarded route redirects)', paths: ['/403'] },
  { name: 'Document upload (FR-08)', paths: ['/upload'] },
  { name: 'Meeting transcripts (FR-09)', paths: ['/meetings'] },
  { name: 'Keyword search, grouped by type (FR-12)', paths: ['/search'] },
  { name: 'Ask, citations and Sources, with the conversation thread (FR-12, FR-13)', paths: ['/ask'] },
  { name: 'Dashboard (FR-14), the landing page for each role', paths: ['/dashboard', '/admin'] },
  {
    name: 'Document repository with filtered browsing, and the document detail view with its download link and deletion (FR-15; FR-08’s retry on its rows)',
    paths: ['/documents', '/documents/:docId'],
  },
]

/* Fixtures for the FR-15 section below: one dimension's values as the browse
   reply carries them, already scoped and counted by the server (D-72). */
const SAMPLE_FACET_VALUES = [
  { value: 'Finance', count: 3 },
  { value: 'Human Resources', count: 2 },
  { value: 'Operations', count: 1 },
]

/* Fixtures for the FR-12 sections below. Invented text, so the sheet shows the
   components without a running AI provider or a corpus; the shapes are the
   contract's own (docs/api-contract.md, Stage 4). */
const SAMPLE_SEARCH_GROUP = {
  count: 2,
  results: [
    {
      source_type: SOURCE_TYPE.document,
      source_id: 'sample-document',
      title: 'Leave policy 2026',
      snippet: '…staff may take annual leave once probation has ended, with their manager’s approval…',
      department: 'People',
      date: '2026-09-21T10:00:00+10:00',
    },
    {
      source_type: SOURCE_TYPE.document,
      source_id: 'sample-document-untitled',
      title: 'Scanned onboarding pack',
      // "" is what a source with no indexed passage carries, matched on its title.
      snippet: '',
      department: '',
      date: '2026-08-02T09:00:00+10:00',
    },
  ],
}

const SAMPLE_SOURCES = [
  {
    source_type: SOURCE_TYPE.document,
    source_id: 'sample-document',
    title: 'Leave policy 2026',
    date: '2026-09-21T10:00:00+10:00',
    passages: [
      { chunk_id: 'sample-chunk-1', text: 'Staff accrue twenty days of annual leave a year, pro rata.' },
    ],
  },
  {
    source_type: SOURCE_TYPE.meeting,
    source_id: 'sample-meeting',
    title: 'People team catch-up',
    date: '2026-09-18T14:00:00+10:00',
    // Consulted without being cited, which is the case the Sources panel exists for.
    passages: [{ chunk_id: 'sample-chunk-3', text: 'We agreed to restate the leave rules in the handbook.' }],
  },
]

// FR-12's partially related items, in the shape the ask reply sends them: source
// identity, title and date, and no passage text — there is no field for one, which
// is the point (apps/retrieval/partial_matches.py). One document and one meeting,
// in the rank order the server put them in.
const SAMPLE_PARTIAL_MATCHES = [
  {
    source_type: SOURCE_TYPE.document,
    source_id: 'sample-document-near-miss',
    title: 'Parental leave guidance',
    date: '2026-07-14T11:30:00+10:00',
  },
  {
    source_type: SOURCE_TYPE.meeting,
    source_id: 'sample-meeting-near-miss',
    title: 'Leave planning, March',
    date: '2026-03-02',
  },
]

const SAMPLE_STATEMENTS = [
  { position: 1, text: 'Staff accrue twenty days of annual leave a year.', chunk_id: 'sample-chunk-1' },
  // Cited, but its passage did not travel with the answer: the number stays as
  // plain text rather than becoming a control that expands nothing.
  { position: 2, text: 'Leave is pro rata for part-time staff.', chunk_id: 'sample-chunk-missing' },
]

const ALL_TOKENS = [
  ...new Set([
    ...COLOR_TOKENS,
    ...SPACING_TOKENS,
    ...FONT_TOKENS,
    ...TYPE_TOKENS,
    ...RADIUS_TOKENS,
    ...FOCUS_TOKENS,
    ...LAYER_TOKENS,
  ]),
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
  // Live demonstrations, so the sheet shows behaviour and not only markup.
  const [demoPassword, setDemoPassword] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const demoRequirementsId = useId()
  // FR-15's browse controls, working against local state here; the repository
  // keeps the same values in the address instead.
  const [demoDepartment, setDemoDepartment] = useState('Finance')
  const [demoSort, setDemoSort] = useState('title')
  const demoFilters = demoDepartment
    ? [{ key: 'department', name: TEXT.repositoryFilterNameDepartment, value: demoDepartment }]
    : []

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

      <section aria-labelledby="sheet-layers">
        <h2 id="sheet-layers">Layers and motion</h2>
        <p>
          Stacking order and the one animation in the interface. The skip link sits above the page, the modal
          scrim above both. <code>--duration-spinner</code> is a single turn of the button&apos;s loading
          indicator; the reduced-motion rule in <code>base.css</code> stops it.
        </p>
        <ul className="token-list">
          {LAYER_TOKENS.map((name) => (
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
          <Button loading disabled>
            Signing in…
          </Button>
        </div>
        <p>
          The loading variant draws the spinner FR-02 asks for and sets <code>aria-busy</code>. The spinner is
          decorative; the label changes with it and is the text equivalent.
        </p>
        <p>
          A link that sits among buttons keeps its link role and takes the secondary button&apos;s look, so a row
          of actions reads as one set. FR-15&apos;s download link on the document detail view is one: following it
          is the browser&apos;s job, not the page&apos;s, so it is an <code>&lt;a&gt;</code> and not a button. Its
          hover keeps the button&apos;s text colour.
        </p>
        <div className="demo-row">
          <a className="btn btn--secondary" href="#sheet-button">
            Link styled as a secondary button
          </a>
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

      <section aria-labelledby="sheet-password">
        <h2 id="sheet-password">Password input and requirements</h2>
        <p>
          FR-02 asks for a &ldquo;Show password&rdquo; toggle and FR-01 for a strength meter shown as the user
          types. The toggle is a real button with <code>aria-pressed</code>; its name stays
          &ldquo;Show password&rdquo; in both states, because a name that flipped to &ldquo;Hide&rdquo; would
          contradict the pressed state. Only the input&apos;s <code>type</code> changes, so focus and caret
          position survive.
        </p>
        <p>
          Each rule is listed with its own met state, carrying a visually hidden &ldquo;Met:&rdquo; or
          &ldquo;Not met:&rdquo; prefix so nothing is conveyed by colour alone. The bar is decorative and
          <code> aria-hidden</code>; the sentence above it is its text equivalent, and a hidden live region
          announces that sentence as it changes. The rules themselves come from
          <code> src/utils/password.js</code>, the one copy of the policy the server enforces.
        </p>
        <div className="demo-stack">
          <PasswordInput
            label="Password"
            name="password-demo"
            autoComplete="new-password"
            value={demoPassword}
            describedBy={demoRequirementsId}
            onChange={(event) => setDemoPassword(event.target.value)}
          />
          <PasswordRequirements id={demoRequirementsId} password={demoPassword} />
          <PasswordInput
            label="Confirm password"
            name="confirm-demo"
            toggleLabel="Show confirmed password"
            autoComplete="new-password"
            defaultValue="different"
            error="The two passwords do not match."
          />
        </div>
      </section>

      <section aria-labelledby="sheet-dialog">
        <h2 id="sheet-dialog">Confirmation dialogue</h2>
        <p>
          FR-05 requires a confirmation before a role change is applied. <code>role=&quot;dialog&quot;</code>{' '}
          with <code>aria-modal</code>, named by its heading and described by its body. Focus moves into it,
          Tab and Shift+Tab cycle inside it, Escape cancels, and focus returns to the control that opened it.
          Open it below and try the keyboard.
        </p>
        <div className="demo-row">
          <Button variant="secondary" onClick={() => setDialogOpen(true)}>
            Show the example dialogue
          </Button>
        </div>
        {dialogOpen ? (
          <Dialog
            title={'Change Jane Doe’s role to Administrator?'}
            confirmLabel="Change role"
            busyLabel="Changing…"
            onConfirm={() => setDialogOpen(false)}
            onCancel={() => setDialogOpen(false)}
          >
            <p>
              Jane Doe (jane@example.com) currently has the Employee role. The change takes effect on their
              next request and is recorded in the audit log.
            </p>
          </Dialog>
        ) : null}
      </section>

      <section aria-labelledby="sheet-select">
        <h2 id="sheet-select">Select</h2>
        <p>
          A native select, so it is keyboard-operable everywhere. The role column on the role management screen
          uses it with a visually hidden label because the column header already names it.
        </p>
        <div className="demo-stack">
          <SelectInput
            label="Role"
            name="role-demo"
            options={[
              { value: 'Employee', label: 'Employee' },
              { value: 'Administrator', label: 'Administrator' },
            ]}
            defaultValue="Employee"
          />
          <SelectInput
            label="Role"
            name="role-error-demo"
            options={[{ value: 'Employee', label: 'Employee' }]}
            defaultValue="Employee"
            error="Choose a valid role."
          />
        </div>
      </section>

      <section aria-labelledby="sheet-textarea">
        <h2 id="sheet-textarea">Text area</h2>
        <div className="demo-stack">
          <TextAreaInput
            label="Transcript"
            name="transcript-demo"
            rows={4}
            hint={TEXT.transcriptVerbatim}
            defaultValue={'[00:03:12] Sagarika: the dates hold.\n[00:03:20] Jordan: agreed.'}
          />
        </div>
        <p>
          FR-09&apos;s pasted transcript. Speaker labels and timestamps are stored exactly as supplied and are
          not parsed, so nothing here treats them as structure.
        </p>
      </section>

      <section aria-labelledby="sheet-dropzone">
        <h2 id="sheet-dropzone">File drop zone</h2>
        <FileDropZone
          label="Choose files"
          hint={TEXT.uploadDropHint}
          accept={FILE_INPUT_ACCEPT}
          multiple
          onFiles={() => {}}
        />
        <p>
          FR-08&apos;s &quot;drag-and-drop or file-picker upload area&quot;, which is both: dragging is a
          pointer gesture, so the picker beside it is the keyboard equivalent. The <code>accept</code>{' '}
          attribute and the format check that follows are conveniences — the server identifies the format from
          the file signature and refuses anything else with a 415.
        </p>
      </section>

      <section aria-labelledby="sheet-progress">
        <h2 id="sheet-progress">Progress bar</h2>
        <div className="demo-stack">
          <ProgressBar label="Upload progress for leave-policy.pdf" value={42} />
          <ProgressBar label="Processing leave-policy.pdf" valueText={TEXT.uploadProcessing} />
        </div>
        <p>
          One per file, as FR-08 requires. The determinate bar carries{' '}
          <code>aria-valuenow</code>; the indeterminate one carries none, because a zero would read as &quot;no
          progress&quot; rather than &quot;unknown&quot;. Both carry the same information as text.
        </p>
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

      <section aria-labelledby="sheet-not-permitted">
        <h2 id="sheet-not-permitted">Not permitted</h2>
        <p>
          Shown where the API answers 403 for material already on screen. A refused navigation is the other
          half of FR-06 and goes to the Access Denied page at <code>/403</code> instead, so an admin URL typed
          by hand does not stay in the address bar. Neither says what the screen would have shown, or whether
          there was anything to show.
        </p>
        <NotPermitted />
      </section>

      <section aria-labelledby="sheet-search-field">
        <h2 id="sheet-search-field">Search field (FR-12)</h2>
        <p>
          The field FR-12 requires "available from every page". It sits in the application header and again at
          the top of the search screen, and both submit to <code>/search?q=</code>. A term shorter than two
          characters is refused here with a message naming the minimum; the server refuses it too, with a 400.
          Submitting this copy navigates to the search screen, as it is the same component.
        </p>
        <SearchField id="sheet-search-field-demo" hint={TEXT.searchHint} />
      </section>

      <section aria-labelledby="sheet-search-results">
        <h2 id="sheet-search-results">Search results (FR-12)</h2>
        <p>
          Results grouped by type with a count per group. Each result shows the four things FR-12 names: its
          title, the matching passage as a snippet, its department, and its date. A group with nothing in it
          still renders with its count, and the count is the server's own post-filter number — there is no
          "showing n of m" anywhere, because no wider figure exists in the reply.
        </p>
        <SearchResultGroup
          heading={TEXT.searchDocumentsHeading}
          headingId="sheet-search-group-documents"
          group={SAMPLE_SEARCH_GROUP}
          emptyMessage={TEXT.searchGroupEmptyDocuments}
        />
        <SearchResultGroup
          heading={TEXT.searchMeetingsHeading}
          headingId="sheet-search-group-meetings"
          group={{ count: 0, results: [] }}
          emptyMessage={TEXT.searchGroupEmptyMeetings}
        />
      </section>

      <section aria-labelledby="sheet-answer">
        <h2 id="sheet-answer">Answer, citations and sources (FR-12)</h2>
        <p>
          Every statement carries a citation, numbered from the <code>position</code> the server stored rather
          than from its place in the array, so the number on the screen and the number on the{' '}
          <code>AnswerCitation</code> row are the same number. Each marker is a button: it expands to the source
          passage and links to the document or meeting it came from. There is no state here for a statement
          without a citation, greyed out or otherwise — the API sends none (CLAUDE.md §6, invariant 6).
        </p>
        <AnswerBody idPrefix="sheet-answer" statements={SAMPLE_STATEMENTS} sources={SAMPLE_SOURCES} />
        <SourcesPanel idPrefix="sheet-answer" sources={SAMPLE_SOURCES} />
      </section>

      <section aria-labelledby="sheet-no-answer">
        <h2 id="sheet-no-answer">No answer, and partial matches (FR-12)</h2>
        <p>
          The platform being unable to answer is a designed outcome, not a failure, so it is an information
          panel and not an error one — and distinct from the 503 above, which means the question could not be
          asked at all. No answer frame is drawn around it and no fragment appears inside it. The partial
          matches beside it are the reply&rsquo;s own <code>partial_matches</code> — the items its
          permission-scoped candidates found, whatever they scored — carrying source identity, title and date
          and no passage text at all, so they are offered as links and never as answer content.
        </p>
        <Notice variant="info" title={TEXT.noAnswerTitle}>
          {TEXT.noAnswerFallback}
        </Notice>
        <PartialMatches idPrefix="sheet-no-answer" results={SAMPLE_PARTIAL_MATCHES} />
      </section>

      <section aria-labelledby="sheet-limits">
        <h2 id="sheet-limits">Limits (D-79, D-85)</h2>
        <p>
          The per-user limits on asking, creating a conversation and adding material. The question still being
          answered is an information panel, not the 503&rsquo;s: nothing is unavailable, and it names no time,
          because the server sends none. A rate limit says when the user can try again, rounded up from the
          reply&rsquo;s <code>Retry-After</code>. The upload limit is the user&rsquo;s and not the file&rsquo;s,
          so a file it held back keeps the neutral status a queued file has, never the danger colour of a refused
          one. So does a file held back because an earlier upload is still being processed (D-85), with its own
          sentence, which names no time either. Every sentence here is the client&rsquo;s own; none is read from
          the reply.
        </p>
        <Notice variant="info" title={TEXT.askInFlightTitle}>
          {TEXT.askInFlight}
        </Notice>
        <Notice variant="error" title={TEXT.askRateLimitedTitle}>
          {TEXT.askRateLimited(TEXT.retryInSeconds(45))}
        </Notice>
        <p className="upload-row__status">
          <span className="upload-status upload-status--limited">{TEXT.uploadLimitedStatus}</span>
          <span className="upload-row__message">{TEXT.uploadLimitReached(TEXT.retryInMinutes(12))}</span>
        </p>
        <p className="upload-row__status">
          <span className="upload-status upload-status--limited">{TEXT.uploadLimitedStatus}</span>
          <span className="upload-row__message">{TEXT.uploadInFlight}</span>
        </p>
      </section>

      <section aria-labelledby="sheet-dashboard-panel">
        <h2 id="sheet-dashboard-panel">Dashboard panel (FR-14)</h2>
        <p>
          A labelled region whose heading links to the module that owns it. While the dashboard&rsquo;s one
          request is in flight each panel says so in words, in a status region, rather than with a spinner alone;
          an empty panel is an ordinary state and says nothing about material outside the reader&rsquo;s scope.
          The indexed total is split by type, with each figure linking to its own module, because the department
          filter narrows only the documents figure (D-70).
        </p>
        <div className="sheet__panels">
          <DashboardPanel
            headingId="sheet-dashboard-loading"
            heading={TEXT.dashboardDocumentsHeading}
            to="/documents"
            loading
            loadingText={TEXT.dashboardLoadingDocuments}
          />
          <DashboardPanel
            headingId="sheet-dashboard-empty"
            heading={TEXT.dashboardMeetingsHeading}
            to="/meetings"
            loadingText={TEXT.dashboardLoadingMeetings}
            empty
            emptyText={TEXT.dashboardNoMeetings}
          />
          <DashboardPanel
            headingId="sheet-dashboard-totals"
            heading={TEXT.dashboardTotalsHeading}
            loadingText={TEXT.dashboardLoadingTotals}
          >
            <dl className="dashboard-totals">
              <div className="dashboard-totals__item">
                <dt>{TEXT.dashboardTotalsDocuments}</dt>
                <dd>4</dd>
              </div>
              <div className="dashboard-totals__item">
                <dt>{TEXT.dashboardTotalsMeetings}</dt>
                <dd>2</dd>
              </div>
              <div className="dashboard-totals__item">
                <dt>{TEXT.dashboardTotalsSum}</dt>
                <dd>6</dd>
              </div>
            </dl>
            <p className="dashboard-panel__note">{TEXT.dashboardTotalsHint}</p>
          </DashboardPanel>
        </div>
      </section>

      <section aria-labelledby="sheet-browse">
        <h2 id="sheet-browse">Filtered browsing (FR-15)</h2>
        <p>
          A browse dimension is a group of toggle buttons, one per value with the server&rsquo;s count beside it.
          The chosen value is filled and ticked, not only coloured, and <code>aria-pressed</code> announces it;
          choosing it again removes it. The count is shown as a number and given its noun for assistive
          technology, so a value reads &ldquo;Finance 3 documents&rdquo;. The values and counts come from the
          documents the reader may see, and a reply with nothing in it (the 204) carries none, so none are shown
          from an earlier reply (D-72).
        </p>
        <div className="demo-stack">
          <FacetGroup
            heading={TEXT.repositoryFilterNameDepartment}
            values={SAMPLE_FACET_VALUES}
            selected={demoDepartment}
            onChoose={setDemoDepartment}
          />
        </div>
        <p>
          The active filters are read from the address, never from a reply, so they are there on the 204 as well.
          Each has its own Remove button, named for the filter it removes, and &ldquo;Clear filters&rdquo; removes
          them all and keeps the sort, which is not a filter.
        </p>
        <ActiveFilterList
          filters={demoFilters}
          onRemove={() => setDemoDepartment('')}
          onClear={() => setDemoDepartment('')}
        />
        <p>
          A sortable column heading is a button inside the <code>th</code>, which carries{' '}
          <code>aria-sort</code> for the column in force. The direction is in words for a screen reader and in an
          arrow on screen. The first press sorts ascending, and a press on the column in force reverses it.
        </p>
        <div className="table-scroll" role="region" aria-labelledby="sheet-browse" tabIndex={0}>
          <table className="contrast-table">
            <caption className="visually-hidden">Example of sortable column headings</caption>
            <thead>
              <tr>
                <SortHeader label={TEXT.repositoryColumnTitle} field="title" sort={demoSort} onSort={setDemoSort} />
                <SortHeader
                  label={TEXT.repositoryColumnUploaded}
                  field="uploaded_at"
                  sort={demoSort}
                  onSort={setDemoSort}
                />
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Leave policy 2026</td>
                <td>21 Sept 2026</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="sheet-built">
        <h2 id="sheet-built">Screens</h2>
        <ul>
          {BUILT.map((screen) => (
            <li key={screen.name}>
              {screen.name}:{' '}
              {screen.paths.map((path, index) => (
                <span key={path}>
                  {index > 0 ? ', ' : ''}
                  <code>{path}</code>
                </span>
              ))}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
