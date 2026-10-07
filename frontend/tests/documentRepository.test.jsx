/**
 * The FR-15 document repository and detail view, rendered against a faked
 * `GET /api/documents/browse`, `GET /api/documents/{id}` and
 * `DELETE /api/documents/{id}` (docs/api-contract.md, "Stage 5 — FR-14, FR-15 /
 * FR-15 — document repository").
 *
 * Each test defends one clause only the interface can satisfy — what the screen
 * shows, withholds or offers. Scoping, the counts, the 204 rule itself, the
 * scoped-first 404 and the 403 are the server's and are tested in pytest; nothing
 * here stands in for them, and the screen filters nothing itself.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import DocumentDetail from '../src/pages/DocumentDetail.jsx'
import DocumentRepository from '../src/pages/DocumentRepository.jsx'
import { formatDate } from '../src/utils/dates.js'
import { serveApi } from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

const LEAVE = {
  doc_id: 'doc-1',
  title: 'Leave policy 2026',
  file_type: 'pdf',
  status: 'Indexed',
  uploaded_at: '2026-09-21T10:00:00+10:00',
  department: 'Human Resources',
  visible_to_roles: ['Employee', 'Administrator'],
  file_size_bytes: 14203,
  uploaded_by: 'erin@example.com',
}

const SUPPLIERS = {
  doc_id: 'doc-2',
  title: 'Supplier review procedure',
  file_type: 'docx',
  status: 'Indexed',
  uploaded_at: '2026-09-18T09:00:00+10:00',
  department: 'Finance',
  visible_to_roles: ['Employee', 'Administrator'],
  file_size_bytes: 20480,
  uploaded_by: 'ada@example.com',
}

/** The contract's browse 200: the filters applied, the facets, the documents. */
function browsePayload(overrides = {}) {
  return {
    filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
    // Counts that cannot be read off the two documents, so a count on screen can
    // only have come from the reply.
    facets: {
      department: [
        { value: 'Finance', count: 3 },
        { value: 'Human Resources', count: 2 },
      ],
      project: [{ value: 'supplier review', count: 4 }],
      process: [{ value: 'purchasing', count: 5 }],
      topic: [
        { value: 'finance', count: 6 },
        { value: 'people', count: 7 },
      ],
    },
    documents: [LEAVE, SUPPLIERS],
    ...overrides,
  }
}

/** The detail object: the document object plus the three detail fields (D-63, D-73). */
function detailOf(record, overrides = {}) {
  return {
    ...record,
    extracted_text: 'Employees may request annual leave.\nRequests go to the line manager.',
    tags: { project: ['policy refresh'], process: [], topic: ['people'] },
    can_delete: false,
    ...overrides,
  }
}

/* ---- Rendering ----------------------------------------------------------- */

/** The router's current location and its Back, as the probe below last saw them. */
const probe = { location: null, back: null }

/** Exposes the router's location and Back to the test, from inside the router. */
function HistoryProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    probe.location = location
    probe.back = () => navigate(-1)
  })
  return null
}

/** The repository and the detail view at their real paths, with a history to go Back through. */
function renderRepository(path = '/documents') {
  probe.location = null
  probe.back = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/documents" element={<DocumentRepository />} />
        <Route path="/documents/:docId" element={<DocumentDetail />} />
      </Routes>
      <HistoryProbe />
    </MemoryRouter>,
  )
  return probe
}

/** The query string of every browse request, in order. */
function browseQueries(answered) {
  return answered.filter((request) => request.path === '/api/documents/browse').map((request) => request.search)
}

/** Every DELETE the screen sent. */
function deletes(answered) {
  return answered.filter((request) => request.method === 'DELETE')
}

/** A column heading's sort button, whether or not it is the column in force. */
function sortButton(label) {
  return screen.getByRole('button', { name: new RegExp(`^${label}(, sorted (ascending|descending))?$`) })
}

function columnHeader(label) {
  return sortButton(label).closest('th')
}

/** One browse dimension's group of values. */
function facetGroup(dimension) {
  return screen.getByRole('region', { name: dimension })
}

/**
 * A click as a browser makes one: the button takes focus, then is clicked.
 * `fireEvent.click` alone moves no focus, which leaves `document.activeElement`
 * on the body and makes every assertion about where focus goes meaningless.
 */
function press(element) {
  element.focus()
  fireEvent.click(element)
}

/** The repository settled on a list, a 204 or a failure: the results status is no longer loading. */
async function settled() {
  await waitFor(() => expect(screen.queryByText(TEXT.loadingDocuments)).toBeNull())
}

/* ---- The list ------------------------------------------------------------ */

describe('FR-15: a list view showing title, type, uploader, upload date and status', () => {
  it('shows each column FR-15 names, including the uploader, and links each title to its detail view', async () => {
    const answered = serveApi({ 'GET /api/documents/browse': { body: browsePayload() } })
    renderRepository()

    const link = await screen.findByRole('link', { name: LEAVE.title })
    expect(link.getAttribute('href')).toBe(`/documents/${LEAVE.doc_id}`)

    const headings = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(headings).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/^Title/),
        expect.stringMatching(/^Type/),
        TEXT.repositoryColumnUploader,
        expect.stringMatching(/^Uploaded(?! by)/),
        expect.stringMatching(/^Status/),
      ]),
    )

    const row = link.closest('tr')
    const cells = within(row)
    expect(cells.getByText(LEAVE.uploaded_by)).toBeTruthy()
    expect(cells.getByText('PDF')).toBeTruthy()
    expect(cells.getByText(formatDate(LEAVE.uploaded_at))).toBeTruthy()
    expect(cells.getByText(LEAVE.status)).toBeTruthy()
    expect(screen.getByText(TEXT.repositoryResultCount(2))).toBeTruthy()
    // An unfiltered address is an unfiltered request: no parameter at all.
    expect(browseQueries(answered)).toEqual([''])
  })
})

describe('FR-15: sorting', () => {
  it('sorts from the column headings, writing the sort to the address and the request', async () => {
    const answered = serveApi({ 'GET /api/documents/browse': { body: browsePayload() } })
    const probe = renderRepository()
    await screen.findByRole('link', { name: LEAVE.title })

    // The server's default, newest first, is shown as the sort in force.
    expect(columnHeader(TEXT.repositoryColumnUploaded).getAttribute('aria-sort')).toBe('descending')

    press(sortButton(TEXT.repositoryColumnTitle))
    await waitFor(() => expect(probe.location.search).toBe('?sort=title'))
    await screen.findByRole('link', { name: LEAVE.title })
    expect(columnHeader(TEXT.repositoryColumnTitle).getAttribute('aria-sort')).toBe('ascending')
    expect(columnHeader(TEXT.repositoryColumnUploaded).getAttribute('aria-sort')).toBeNull()
    // Focus comes back to the heading that was pressed once the list re-renders.
    expect(document.activeElement).toBe(sortButton(TEXT.repositoryColumnTitle))

    press(sortButton(TEXT.repositoryColumnTitle))
    await waitFor(() => expect(probe.location.search).toBe('?sort=-title'))
    await screen.findByRole('link', { name: LEAVE.title })
    expect(columnHeader(TEXT.repositoryColumnTitle).getAttribute('aria-sort')).toBe('descending')

    fireEvent.click(sortButton(TEXT.repositoryColumnUploader))
    await waitFor(() => expect(probe.location.search).toBe('?sort=uploaded_by'))
    await screen.findByRole('link', { name: LEAVE.title })

    expect(browseQueries(answered)).toEqual(['', '?sort=title', '?sort=-title', '?sort=uploaded_by'])
  })
})

describe('FR-15: text filtering', () => {
  it('writes the title filter to the address and the request when it is submitted', async () => {
    const answered = serveApi({ 'GET /api/documents/browse': { body: browsePayload({ documents: [LEAVE] }) } })
    const probe = renderRepository()
    await screen.findByRole('link', { name: LEAVE.title })

    const field = screen.getByLabelText(TEXT.repositoryFilterLabel)
    fireEvent.change(field, { target: { value: 'leave' } })
    // Typing alone sends nothing and changes no address.
    expect(probe.location.search).toBe('')
    fireEvent.click(screen.getByRole('button', { name: TEXT.repositoryFilterSubmit }))

    await waitFor(() => expect(probe.location.search).toBe('?q=leave'))
    await settled()
    expect(browseQueries(answered)).toEqual(['', '?q=leave'])
    const active = screen.getByRole('region', { name: TEXT.repositoryActiveFilters })
    expect(active.textContent).toContain(`${TEXT.repositoryFilterNameQ}: leave`)
    expect(screen.getByLabelText(TEXT.repositoryFilterLabel).value).toBe('leave')
  })
})

describe('FR-15: browsing by Department, Project, Process or Topic, with counts, filters combining', () => {
  it('lists each dimension with the counts the server sent, and choosing values updates the address and the request', async () => {
    const answered = serveApi({ 'GET /api/documents/browse': { body: browsePayload() } })
    const probe = renderRepository()
    await screen.findByRole('link', { name: LEAVE.title })

    // Every value of every dimension, each with the count the server sent, in its
    // order, and nothing else: one button per value, named by value and count.
    for (const [dimension, values] of [
      [TEXT.repositoryFilterNameDepartment, [['Finance', 3], ['Human Resources', 2]]],
      [TEXT.repositoryFilterNameProject, [['supplier review', 4]]],
      [TEXT.repositoryFilterNameProcess, [['purchasing', 5]]],
      [TEXT.repositoryFilterNameTopic, [['finance', 6], ['people', 7]]],
    ]) {
      const group = within(facetGroup(dimension))
      const buttons = group.getAllByRole('button')
      expect(buttons).toHaveLength(values.length)
      values.forEach(([value, count], index) => {
        expect(group.getByRole('button', { name: `${value} ${TEXT.repositoryFacetCount(count)}` })).toBe(buttons[index])
      })
    }
    // The number is on screen, and its noun is given to assistive technology.
    const financeCount = within(facetGroup(TEXT.repositoryFilterNameDepartment)).getByText('3')
    expect(financeCount.getAttribute('aria-hidden')).toBe('true')

    const finance = within(facetGroup(TEXT.repositoryFilterNameDepartment)).getByRole('button', {
      name: `Finance ${TEXT.repositoryFacetCount(3)}`,
    })
    expect(finance.getAttribute('aria-pressed')).toBe('false')
    press(finance)
    await waitFor(() => expect(probe.location.search).toBe('?department=Finance'))
    await settled()

    // The pressed value stays where it was, pressed, and keeps the focus.
    const pressed = within(facetGroup(TEXT.repositoryFilterNameDepartment)).getByRole('button', {
      name: `Finance ${TEXT.repositoryFacetCount(3)}`,
    })
    expect(pressed.getAttribute('aria-pressed')).toBe('true')
    expect(document.activeElement).toBe(pressed)

    // A second dimension combines with the first.
    fireEvent.click(
      within(facetGroup(TEXT.repositoryFilterNameProcess)).getByRole('button', {
        name: `purchasing ${TEXT.repositoryFacetCount(5)}`,
      }),
    )
    await waitFor(() => expect(probe.location.search).toBe('?department=Finance&process=purchasing'))
    await settled()

    const active = screen.getByRole('region', { name: TEXT.repositoryActiveFilters })
    expect(active.textContent).toContain(`${TEXT.repositoryFilterNameDepartment}: Finance`)
    expect(active.textContent).toContain(`${TEXT.repositoryFilterNameProcess}: purchasing`)

    // Each active filter can be removed on its own.
    fireEvent.click(
      screen.getByRole('button', {
        name: TEXT.repositoryRemoveFilterLabel(TEXT.repositoryFilterNameDepartment, 'Finance'),
      }),
    )
    await waitFor(() => expect(probe.location.search).toBe('?process=purchasing'))
    await settled()

    expect(browseQueries(answered)).toEqual([
      '',
      '?department=Finance',
      '?department=Finance&process=purchasing',
      '?process=purchasing',
    ])
  })
})

/* ---- The 204 ------------------------------------------------------------- */

/** A browse route that answers 204 to any filter, as the server does when nothing in scope matches. */
function nothingMatchesAnyFilter(url) {
  const filtered = ['q', 'status', 'department', 'project', 'process', 'topic'].some((key) => url.searchParams.get(key))
  return filtered ? { status: 204 } : { body: browsePayload() }
}

describe('D-72: the 204, a filter combination with no accessible matches', () => {
  it('on a filtered address opened directly, shows the empty state, the filters from the address and Clear filters, and assumes no facets', async () => {
    // Opened fresh — a bookmark, or Back after a delete — so there has never been
    // a reply carrying facets for this screen to fall back on.
    const answered = serveApi({ 'GET /api/documents/browse': nothingMatchesAnyFilter })
    const probe = renderRepository('/documents?q=leave&department=Finance&topic=finance')

    expect(await screen.findByText(TEXT.repositoryNoMatchTitle)).toBeTruthy()
    expect(screen.getByText(TEXT.repositoryNoMatch)).toBeTruthy()
    // An ordinary state, not an error.
    expect(screen.queryByRole('alert')).toBeNull()

    // The active filters, read from the address.
    const active = screen.getByRole('region', { name: TEXT.repositoryActiveFilters })
    expect(active.textContent).toContain(`${TEXT.repositoryFilterNameQ}: leave`)
    expect(active.textContent).toContain(`${TEXT.repositoryFilterNameDepartment}: Finance`)
    expect(active.textContent).toContain(`${TEXT.repositoryFilterNameTopic}: finance`)
    for (const [name, value] of [
      [TEXT.repositoryFilterNameQ, 'leave'],
      [TEXT.repositoryFilterNameDepartment, 'Finance'],
      [TEXT.repositoryFilterNameTopic, 'finance'],
    ]) {
      expect(screen.getByRole('button', { name: TEXT.repositoryRemoveFilterLabel(name, value) })).toBeTruthy()
    }
    expect(screen.getByLabelText(TEXT.repositoryFilterLabel).value).toBe('leave')

    // No facets, and no list: there was no reply to take either from.
    expect(document.querySelectorAll('[aria-pressed]')).toHaveLength(0)
    expect(screen.getByText(TEXT.repositoryBrowseNoMatch)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(browseQueries(answered)).toEqual(['?q=leave&department=Finance&topic=finance'])

    fireEvent.click(screen.getByRole('button', { name: TEXT.repositoryClearFilters }))
    await waitFor(() => expect(probe.location.search).toBe(''))
    expect(await screen.findByRole('link', { name: LEAVE.title })).toBeTruthy()
    expect(screen.queryByText(TEXT.repositoryNoMatchTitle)).toBeNull()
    expect(browseQueries(answered)).toEqual(['?q=leave&department=Finance&topic=finance', ''])
  })

  it('drops the facets an earlier reply carried when a later one is a 204', async () => {
    serveApi({ 'GET /api/documents/browse': nothingMatchesAnyFilter })
    renderRepository()
    await screen.findByRole('link', { name: LEAVE.title })
    expect(document.querySelectorAll('[aria-pressed]').length).toBeGreaterThan(0)

    press(
      within(facetGroup(TEXT.repositoryFilterNameDepartment)).getByRole('button', {
        name: `Finance ${TEXT.repositoryFacetCount(3)}`,
      }),
    )

    expect(await screen.findByText(TEXT.repositoryNoMatchTitle)).toBeTruthy()
    expect(document.querySelectorAll('[aria-pressed]')).toHaveLength(0)
    const browse = screen.getByRole('region', { name: TEXT.repositoryBrowseHeading })
    expect(browse.textContent).not.toContain('Human Resources')
    expect(browse.textContent).toContain(TEXT.repositoryBrowseNoMatch)
    // The pressed button went with the facets, so focus is put somewhere deliberate.
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: TEXT.repositoryResultsHeading }))
  })
})

/* ---- The round trip ------------------------------------------------------ */

describe('D-61 gap 3: the filters survive a round trip through a detail view', () => {
  it('lands on the same address, the same controls and the same request after opening a document and going Back', async () => {
    const answered = serveApi({
      'GET /api/documents/browse': { body: browsePayload() },
      [`GET /api/documents/${LEAVE.doc_id}`]: { body: detailOf(LEAVE) },
    })
    const probe = renderRepository()
    await screen.findByRole('link', { name: LEAVE.title })

    // Every kind of state the screen has: a browse value, the text filter, a sort.
    fireEvent.click(
      within(facetGroup(TEXT.repositoryFilterNameTopic)).getByRole('button', {
        name: `people ${TEXT.repositoryFacetCount(7)}`,
      }),
    )
    await settled()
    fireEvent.change(screen.getByLabelText(TEXT.repositoryFilterLabel), { target: { value: 'policy' } })
    fireEvent.click(screen.getByRole('button', { name: TEXT.repositoryFilterSubmit }))
    await settled()
    fireEvent.click(sortButton(TEXT.repositoryColumnTitle))
    await settled()

    const filtered = '?q=policy&topic=people&sort=title'
    expect(probe.location.search).toBe(filtered)
    const before = browseQueries(answered)
    expect(before.at(-1)).toBe(filtered)

    // Into the detail view, whose own link back carries the same filters.
    fireEvent.click(await screen.findByRole('link', { name: LEAVE.title }))
    await screen.findByRole('heading', { level: 1, name: LEAVE.title })
    expect(probe.location.pathname).toBe(`/documents/${LEAVE.doc_id}`)
    expect(screen.getByRole('link', { name: TEXT.documentBackToList }).getAttribute('href')).toBe(
      `/documents${filtered}`,
    )

    act(() => probe.back())
    await screen.findByRole('link', { name: LEAVE.title })

    expect(probe.location.pathname).toBe('/documents')
    expect(probe.location.search).toBe(filtered)
    expect(screen.getByLabelText(TEXT.repositoryFilterLabel).value).toBe('policy')
    expect(
      within(facetGroup(TEXT.repositoryFilterNameTopic))
        .getByRole('button', { name: `people ${TEXT.repositoryFacetCount(7)}` })
        .getAttribute('aria-pressed'),
    ).toBe('true')
    expect(columnHeader(TEXT.repositoryColumnTitle).getAttribute('aria-sort')).toBe('ascending')
    // The same request again, and nothing else.
    expect(browseQueries(answered)).toEqual([...before, filtered])
  })
})

/* ---- The detail view ----------------------------------------------------- */

/** The detail view at its path, for a document the fake API describes. */
async function renderDetail(detail, extraRoutes = {}, path = `/documents/${detail.doc_id}`) {
  const answered = serveApi({ [`GET /api/documents/${detail.doc_id}`]: { body: detail }, ...extraRoutes })
  const probe = renderRepository(path)
  await screen.findByRole('heading', { level: 1, name: detail.title })
  return { answered, probe }
}

describe('FR-15 detail view: metadata', () => {
  it('shows the metadata and the tags by dimension', async () => {
    await renderDetail(detailOf(LEAVE))

    const meta = document.querySelector('dl')
    const fields = Object.fromEntries(
      Array.from(meta.querySelectorAll('dt')).map((term) => [term.textContent, term.nextElementSibling.textContent]),
    )
    expect(fields).toEqual({
      [TEXT.documentFieldType]: 'PDF',
      [TEXT.documentFieldUploader]: LEAVE.uploaded_by,
      [TEXT.documentFieldUploaded]: formatDate(LEAVE.uploaded_at),
      [TEXT.documentFieldStatus]: LEAVE.status,
      [TEXT.documentFieldDepartment]: LEAVE.department,
      [TEXT.documentFieldVisibleTo]: 'Employee, Administrator',
      [TEXT.documentFieldProject]: 'policy refresh',
      [TEXT.documentFieldProcess]: TEXT.documentNoTags,
      [TEXT.documentFieldTopic]: 'people',
    })
  })
})

describe('D-63: extracted content is rendered as text, never as HTML', () => {
  it('shows markup in the extracted text as the characters it is, and creates no element from it', async () => {
    const hostile =
      'Line one of the policy.\n' +
      'Line two <b>bold</b><script>window.__fr15Injected = true</script>' +
      '<img src="x" onerror="window.__fr15Injected = true">'
    await renderDetail(detailOf(LEAVE, { extracted_text: hostile }))

    const region = screen.getByRole('region', { name: TEXT.documentExtractedHeading })
    // Exactly the string, line break included: kept by CSS, not turned into markup.
    expect(region.textContent).toBe(hostile)
    expect(region.children).toHaveLength(0)
    expect(region.querySelector('b, script, img, br')).toBeNull()
    expect(document.querySelectorAll('script, img')).toHaveLength(0)
    expect(window.__fr15Injected).toBeUndefined()
    expect(screen.queryByText(TEXT.documentExtractedEmpty)).toBeNull()
  })

  it('shows the stated empty state when extracted_text is null, keyed on the null and not on the status', async () => {
    // "Indexed" with no extracted content: a status that usually has text, so an
    // empty state keyed on the status would get this one wrong.
    await renderDetail(detailOf(LEAVE, { status: 'Indexed', extracted_text: null }))

    expect(screen.getByText(TEXT.documentExtractedEmpty)).toBeTruthy()
    expect(screen.queryByRole('region', { name: TEXT.documentExtractedHeading })).toBeNull()
  })

  it('shows the text of a document whose status is a failure, when the detail carries text', async () => {
    const text = 'Recovered text from a document whose status says it failed.'
    await renderDetail(detailOf(SUPPLIERS, { status: 'Indexing failed', extracted_text: text }))

    expect(screen.getByRole('region', { name: TEXT.documentExtractedHeading }).textContent).toBe(text)
    expect(screen.queryByText(TEXT.documentExtractedEmpty)).toBeNull()
  })
})

describe('FR-15 deletion: offered only with manage_documents, and only after confirmation', () => {
  it('offers no delete control when can_delete is false', async () => {
    await renderDetail(detailOf(LEAVE, { can_delete: false }))

    expect(screen.queryByRole('button', { name: TEXT.documentDelete })).toBeNull()
    expect(screen.queryAllByRole('button').filter((button) => /delete/i.test(button.textContent))).toEqual([])
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('asks for confirmation before sending anything, and Cancel sends no DELETE', async () => {
    const { answered } = await renderDetail(detailOf(LEAVE, { can_delete: true }), {
      [`DELETE /api/documents/${LEAVE.doc_id}`]: { status: 204 },
    })

    const control = screen.getByRole('button', { name: TEXT.documentDelete })
    press(control)

    const dialog = screen.getByRole('dialog', { name: TEXT.documentDeleteConfirm(LEAVE.title) })
    expect(dialog.textContent).toContain(TEXT.documentDeleteBody)
    // Opening the dialogue sends nothing.
    expect(deletes(answered)).toEqual([])

    fireEvent.click(within(dialog).getByRole('button', { name: TEXT.documentDeleteCancel }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(deletes(answered)).toEqual([])
    // The record is still on screen, and focus is back on the control that opened it.
    expect(screen.getByRole('heading', { level: 1, name: LEAVE.title })).toBeTruthy()
    expect(document.activeElement).toBe(control)
  })

  it('sends exactly one DELETE on confirm, then returns to the repository at the filters the user came from', async () => {
    const answered = serveApi({
      'GET /api/documents/browse': (url) =>
        url.searchParams.get('department') === 'Finance' ? { body: browsePayload({ documents: [SUPPLIERS] }) } : { body: browsePayload() },
      [`GET /api/documents/${SUPPLIERS.doc_id}`]: { body: detailOf(SUPPLIERS, { can_delete: true }) },
      [`DELETE /api/documents/${SUPPLIERS.doc_id}`]: { status: 204 },
    })
    const probe = renderRepository('/documents?department=Finance')
    fireEvent.click(await screen.findByRole('link', { name: SUPPLIERS.title }))
    await screen.findByRole('heading', { level: 1, name: SUPPLIERS.title })

    fireEvent.click(screen.getByRole('button', { name: TEXT.documentDelete }))
    const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.documentDelete })
    // Pressed twice, as an impatient user does: still one request.
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    expect(await screen.findByText(TEXT.repositoryDeleted(SUPPLIERS.title))).toBeTruthy()
    expect(deletes(answered)).toEqual([
      { method: 'DELETE', path: `/api/documents/${SUPPLIERS.doc_id}`, search: '', body: undefined },
    ])
    expect(probe.location.pathname).toBe('/documents')
    expect(probe.location.search).toBe('?department=Finance')
    expect(browseQueries(answered)).toEqual(['?department=Finance', '?department=Finance'])
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('says so when the server refuses the delete with a 403, and withdraws the control', async () => {
    const { answered } = await renderDetail(detailOf(LEAVE, { can_delete: true }), {
      [`DELETE /api/documents/${LEAVE.doc_id}`]: { status: 403, body: { detail: 'You do not have permission to perform this action.' } },
    })

    fireEvent.click(screen.getByRole('button', { name: TEXT.documentDelete }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.documentDelete }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.documentDeleteFailed)
    expect(alert.textContent).toContain(TEXT.documentDeleteNotPermitted)
    expect(screen.queryByRole('button', { name: TEXT.documentDelete })).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
    // Still on the record, which the 403 did not remove.
    expect(screen.getByRole('heading', { level: 1, name: LEAVE.title })).toBeTruthy()
    expect(deletes(answered)).toHaveLength(1)
  })
})

describe('FR-15 failure states', () => {
  it('shows a failed list as an error, never with the backend text, and retries', async () => {
    let attempts = 0
    const backendText = 'Traceback (most recent call last): relation "documents" does not exist'
    serveApi({
      'GET /api/documents/browse': () => {
        attempts += 1
        return attempts === 1 ? { status: 500, body: { detail: backendText } } : { body: browsePayload() }
      },
    })
    renderRepository()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.documentsLoadFailed)
    expect(document.body.textContent).not.toContain(backendText)

    fireEvent.click(screen.getByRole('button', { name: TEXT.uploadRetry }))
    expect(await screen.findByRole('link', { name: LEAVE.title })).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows a 404 as not found, never which kind, with a way back to the repository', async () => {
    serveApi({ 'GET /api/documents/missing': { status: 404, body: { detail: 'Not found.' } } })
    renderRepository('/documents/missing')

    expect(await screen.findByText(TEXT.documentRecordNotFound)).toBeTruthy()
    expect(screen.getByRole('link', { name: TEXT.documentBackToList }).getAttribute('href')).toBe('/documents')
  })
})
