/**
 * A link that shares its line with other text keeps its underline (NFR-16:
 * WCAG 2.1 SC 1.4.1, use of colour).
 *
 * `.repository-page` is the page frame of the Ask, document, meeting and
 * repository screens, so a rule written there for the repository's upload link
 * reaches every link in every paragraph of those screens. An answer's source
 * line, "Leave policy · Document · 1 August 2026 View the document", carries its
 * link beside other text. Without the underline only colour sets it apart, and
 * --color-primary against that line's text is 2.20:1 on body text and 1.13:1 on
 * muted text, under the 3:1 a colour-only difference would need (WCAG technique
 * G183). jsdom applies no stylesheet, so the rules are read from disk
 * (tests/stylesheets.js) and matched against the rendered link.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import { answeredReply, CONVERSATION, serveApi } from './fakeApi.js'
import { resolve, rulesMatching } from './stylesheets.js'

/** The rules matching `link` that take its underline away, as "file:line selector". */
function underlineRemovers(link) {
  return rulesMatching(link)
    .filter((rule) =>
      rule.declarations.some(
        (declaration) =>
          ['text-decoration', 'text-decoration-line'].includes(declaration.property) &&
          /^none\b/.test(resolve(declaration.value).trim().toLowerCase()),
      ),
    )
    .map((rule) => `${rule.file}:${rule.line} ${rule.selector}`)
}

describe('SC 1.4.1: a link inside a line of text on a repository-frame screen keeps its underline', () => {
  it('leaves the underline on an answer’s "View the document", which sits in its source line', async () => {
    serveApi({
      'GET /api/conversations': { body: [] },
      'POST /api/conversations': { status: 201, body: CONVERSATION },
      'POST /api/ask': { body: answeredReply() },
    })
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <Ask />
      </MemoryRouter>,
    )
    await screen.findByText(TEXT.noConversations)
    fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), {
      target: { value: 'How much annual leave do I get?' },
    })
    fireEvent.click(screen.getByRole('button', { name: TEXT.askSubmit }))

    const links = await screen.findAllByRole('link', { name: TEXT.viewDocument })
    for (const link of links) {
      // On a screen the repository's page frame wraps, inside a paragraph, beside other text.
      expect(link.closest('.repository-page')).not.toBeNull()
      const line = link.closest('p')
      expect(line).not.toBeNull()
      expect(line.textContent.replace(link.textContent, '').trim()).not.toBe('')

      expect(underlineRemovers(link)).toEqual([])
    }
  })
})
