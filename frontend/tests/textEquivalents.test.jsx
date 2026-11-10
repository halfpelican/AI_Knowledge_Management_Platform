/**
 * Text equivalents for non-text content (Stage 5 item 7; WCAG 2.1 SC 1.1.1,
 * which NFR-17 cites as the measure for anything graphical).
 *
 * Every non-text representation in the shared components — bars, glyphs,
 * markers, spinners — must carry the same information as text a screen reader
 * reaches, and the decoration itself must be aria-hidden so it is not read as
 * noise. Each test names the component and the equivalent it defends.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AnswerBody } from '../src/components/Answer.jsx'
import { FacetGroup, SortHeader } from '../src/components/Browse.jsx'
import Button from '../src/components/Button.jsx'
import PasswordRequirements from '../src/components/PasswordRequirements.jsx'
import ProgressBar from '../src/components/ProgressBar.jsx'
import { TEXT } from '../src/constants.js'

describe('FR-08: the progress bar carries its state as text', () => {
  it('a determinate bar names its file and holds the percentage as value, text and visible figure', () => {
    render(<ProgressBar label="Upload progress for leave-policy.pdf" value={42} />)
    const bar = screen.getByRole('progressbar', { name: 'Upload progress for leave-policy.pdf' })
    expect(bar.getAttribute('aria-valuenow')).toBe('42')
    expect(bar.getAttribute('aria-valuetext')).toBe('42%')
    // The filled band is decoration; the figure beside the track repeats the
    // value for sighted readers and is hidden from assistive technology, which
    // already has it on the progressbar itself.
    expect(bar.querySelector('.progress__fill').getAttribute('aria-hidden')).toBe('true')
    const figure = screen.getByText('42%')
    expect(figure.getAttribute('aria-hidden')).toBe('true')
  })

  it('an indeterminate bar carries no value — zero would read as "no progress" — and says what it is doing', () => {
    render(<ProgressBar label="Processing leave-policy.pdf" valueText={TEXT.uploadProcessing} />)
    const bar = screen.getByRole('progressbar', { name: 'Processing leave-policy.pdf' })
    expect(bar.getAttribute('aria-valuenow')).toBeNull()
    expect(bar.getAttribute('aria-valuetext')).toBe(TEXT.uploadProcessing)
  })
})

describe('FR-15: the browse value and the sort arrow read as words', () => {
  it('a facet reads as its value and a counted noun, with the bare number hidden as decoration', () => {
    render(
      <FacetGroup
        heading="Department"
        values={[{ value: 'Finance', count: 3 }]}
        selected=""
        onChoose={() => {}}
      />,
    )
    const facet = screen.getByRole('button', { name: `Finance ${TEXT.repositoryFacetCount(3)}` })
    expect(within(facet).getByText('3').getAttribute('aria-hidden')).toBe('true')
  })

  it('a sorted column names its direction in words; the arrow glyph is decoration', () => {
    render(
      <table>
        <thead>
          <tr>
            <SortHeader label="Uploaded" field="uploaded_at" sort="-uploaded_at" onSort={() => {}} />
          </tr>
        </thead>
      </table>,
    )
    const button = screen.getByRole('button', {
      name: new RegExp(`^Uploaded\\s*, ${TEXT.repositorySortedDescending}$`),
    })
    expect(within(button).getByText('▼').getAttribute('aria-hidden')).toBe('true')
    expect(button.closest('th').getAttribute('aria-sort')).toBe('descending')
  })
})

describe('FR-12: the citation marker is named, not a bare bracket', () => {
  it('reads as "Source for statement n" with the visible [n] hidden as decoration', () => {
    const statements = [{ position: 1, text: 'Staff accrue twenty days of annual leave a year.', chunk_id: 'chunk-1' }]
    const sources = [
      {
        source_type: 'document',
        source_id: 'doc-1',
        title: 'Leave policy 2026',
        date: '2026-09-21T10:00:00+10:00',
        passages: [{ chunk_id: 'chunk-1', text: 'Staff accrue twenty days of annual leave a year, pro rata.' }],
      },
    ]
    render(
      <MemoryRouter>
        <AnswerBody idPrefix="test" statements={statements} sources={sources} />
      </MemoryRouter>,
    )
    const marker = screen.getByRole('button', { name: TEXT.citationToggleLabel(1) })
    expect(within(marker).getByText('[1]').getAttribute('aria-hidden')).toBe('true')
    expect(marker.getAttribute('aria-expanded')).toBe('false')
  })
})

describe('FR-02: the loading button spins for the eye and speaks through its label', () => {
  it('marks the spinner decorative and the button busy while the label says what is happening', () => {
    render(
      <Button loading disabled>
        Signing in…
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Signing in…' })
    expect(button.getAttribute('aria-busy')).toBe('true')
    expect(button.querySelector('.btn__spinner').getAttribute('aria-hidden')).toBe('true')
  })
})

describe('FR-01: the strength meter is decoration beside a sentence that says the same', () => {
  it('hides the bar, keeps the summary sentence visible, and prefixes each rule with its met state in text', () => {
    const { container } = render(<PasswordRequirements id="req" password="Tr0ub4dor" />)
    expect(container.querySelector('.password-req__meter').getAttribute('aria-hidden')).toBe('true')
    // The sentence is the meter's text equivalent. It appears twice — once on
    // the screen, once in the live region that announces changes — and the
    // on-screen copy must not be hidden.
    const summaries = screen.getAllByText(/Password strength:/)
    expect(summaries.some((sentence) => sentence.closest('.visually-hidden') === null)).toBe(true)
    // Met and not met are words, so no rule's state is carried by colour alone
    // (SC 1.4.1); the glyphs are decoration.
    expect(screen.getAllByText(/^(Met:|Not met:)$/).length).toBeGreaterThan(0)
    for (const glyph of container.querySelectorAll('.password-req__glyph')) {
      expect(glyph.getAttribute('aria-hidden')).toBe('true')
    }
  })
})

describe('nothing interactive hides inside aria-hidden decoration', () => {
  it('keeps every aria-hidden subtree free of focusable elements', () => {
    const statements = [{ position: 1, text: 'Statement.', chunk_id: 'chunk-1' }]
    const sources = [
      {
        source_type: 'document',
        source_id: 'doc-1',
        title: 'Leave policy 2026',
        date: '2026-09-21T10:00:00+10:00',
        passages: [{ chunk_id: 'chunk-1', text: 'Passage.' }],
      },
    ]
    render(
      <MemoryRouter>
        <div>
          <ProgressBar label="Upload progress" value={42} />
          <Button loading>Working…</Button>
          <PasswordRequirements id="req" password="x" />
          <FacetGroup heading="Department" values={[{ value: 'Finance', count: 3 }]} selected="" onChoose={() => {}} />
          <AnswerBody idPrefix="sweep" statements={statements} sources={sources} />
        </div>
      </MemoryRouter>,
    )
    // Both shapes of the failure: a focusable element inside aria-hidden
    // decoration, and decoration that is itself made focusable.
    const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    const offenders = [...document.querySelectorAll(FOCUSABLE)].filter(
      (el) => el.closest('[aria-hidden="true"]') !== null,
    )
    expect(offenders.map((el) => el.outerHTML.slice(0, 60))).toEqual([])
  })
})
