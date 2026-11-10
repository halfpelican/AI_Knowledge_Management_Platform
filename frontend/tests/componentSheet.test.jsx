/**
 * The component sheet is the style guide NFR-14 names, and Stage 5 item 7 asks
 * for it complete: every shared component in its states, including the meeting
 * delete control D-99 added. These tests hold the sheet to that, so a component
 * or state added to the screens without a sheet entry fails here rather than
 * drifting.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import ComponentSheet from '../src/components/ComponentSheet.jsx'
import { CONTRAST_PAIRS } from '../src/components/contrastPairs.js'
import { TEXT } from '../src/constants.js'
import { contrast, tokenColour } from './stylesheets.js'

function renderSheet() {
  render(
    <MemoryRouter initialEntries={['/components']}>
      <ComponentSheet />
    </MemoryRouter>,
  )
}

describe('the sheet shows every shared component in its states', () => {
  it('shows the button in primary, secondary, disabled and loading states', () => {
    renderSheet()
    expect(screen.getByRole('button', { name: 'Primary' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Secondary' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Primary disabled' }).disabled).toBe(true)
    const loading = screen.getByRole('button', { name: 'Signing in…' })
    expect(loading.getAttribute('aria-busy')).toBe('true')
  })

  it('shows the drop zone in its default state with a status, and disabled with its reason', () => {
    renderSheet()
    expect(screen.getByText(TEXT.dropZoneAdded(['leave-policy.pdf'], 0))).toBeTruthy()
    expect(screen.getByText(TEXT.dropZoneBusy)).toBeTruthy()
    const inputs = screen.getAllByLabelText('Choose files')
    expect(inputs.some((input) => input.disabled)).toBe(true)
    expect(inputs.some((input) => !input.disabled)).toBe(true)
  })

  it('shows the attendee picker with a recorded person, their Remove, and the add control', () => {
    renderSheet()
    const list = screen.getByRole('list', { name: TEXT.attendeeListLabel })
    expect(within(list).getByText('Ada Admin (ada@example.com)')).toBeTruthy()
    expect(
      within(list).getByRole('button', { name: TEXT.attendeeRemoveLabel('Ada Admin (ada@example.com)') }),
    ).toBeTruthy()
    expect(screen.getByLabelText(TEXT.attendeeAddLabel)).toBeTruthy()
  })

  it("shows D-99's meeting delete control, and its confirmation says what goes", () => {
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: TEXT.meetingDelete }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(TEXT.meetingDeleteBody)).toBeTruthy()
    expect(within(dialog).getByRole('button', { name: TEXT.meetingDelete })).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: TEXT.meetingDeleteCancel }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('shows the error, empty, loading and no-answer states the screens use', () => {
    renderSheet()
    // Inputs in their error state.
    expect(screen.getByText('Enter a valid email address.')).toBeTruthy()
    expect(screen.getByText('The two passwords do not match.')).toBeTruthy()
    // The three notice variants, the 503 included (NFR-19).
    expect(screen.getByText('Processing failed. Please try again.')).toBeTruthy()
    expect(screen.getByText('The AI service is currently unavailable. Please try again shortly.')).toBeTruthy()
    // The no-answer state is a designed outcome with its own panel.
    expect(screen.getByText(TEXT.noAnswerTitle)).toBeTruthy()
    // A loading and an empty dashboard panel.
    expect(screen.getByText(TEXT.dashboardLoadingDocuments)).toBeTruthy()
    expect(screen.getByText(TEXT.dashboardNoMeetings)).toBeTruthy()
  })

  it('documents contrast pairs that pass their bars, one rendered row per pair', () => {
    // In the browser the sheet computes ratios from the live custom
    // properties; jsdom applies no stylesheet, so here each documented pair is
    // recomputed from tokens.css on disk. A pair the sheet claims that no
    // longer passes fails here.
    for (const pair of CONTRAST_PAIRS) {
      const ratio = contrast(tokenColour(pair.fg), tokenColour(pair.bg))
      expect(ratio, `${pair.label}: ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(pair.minimum)
    }
    renderSheet()
    const table = screen.getByRole('table', { name: 'Contrast ratio of each text and background pair' })
    expect(within(table).getAllByRole('row')).toHaveLength(CONTRAST_PAIRS.length + 1)
  })
})
