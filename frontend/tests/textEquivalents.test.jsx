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
import { KNOWLEDGE_MAP_NODE_TYPE, KNOWLEDGE_MAP_RELATIONSHIP, TEXT } from '../src/constants.js'
import { KnowledgeMapDiagram, KnowledgeMapLegend } from '../src/pages/KnowledgeMap.jsx'

/* FR-20's diagram (D-132), from sample data: one node of each type, the document
   selected, and a line for each kind of relationship. */
const MAP_NODES = [
  { id: 'document:d1', type: KNOWLEDGE_MAP_NODE_TYPE.document, item_id: 'd1', label: 'Leave policy 2026', dimension: null, connection_count: 2 },
  { id: 'tag:t1', type: KNOWLEDGE_MAP_NODE_TYPE.tag, item_id: 't1', label: 'people', dimension: 'Topic', connection_count: 1 },
  { id: 'contributor:u1', type: KNOWLEDGE_MAP_NODE_TYPE.contributor, item_id: 'u1', label: 'Jane Doe', dimension: null, connection_count: 2 },
  { id: 'meeting:m1', type: KNOWLEDGE_MAP_NODE_TYPE.meeting, item_id: 'm1', label: 'Q3 planning sync', dimension: null, connection_count: 1 },
]

function mapRelationship(source, relationship, target) {
  return { key: `${source.id}|${relationship}|${target.id}`, relationship, source, target }
}

const MAP_RELATIONSHIPS = [
  mapRelationship(MAP_NODES[0], KNOWLEDGE_MAP_RELATIONSHIP.tagged, MAP_NODES[1]),
  mapRelationship(MAP_NODES[2], KNOWLEDGE_MAP_RELATIONSHIP.uploaded, MAP_NODES[0]),
  mapRelationship(MAP_NODES[2], KNOWLEDGE_MAP_RELATIONSHIP.attended, MAP_NODES[3]),
]

/** The legend and the diagram as the knowledge map page puts them together. */
function SampleMap() {
  return (
    <div>
      <KnowledgeMapLegend />
      <h2 id="sample-map-heading">{TEXT.mapDiagramHeading}</h2>
      <KnowledgeMapDiagram
        nodes={MAP_NODES}
        relationships={MAP_RELATIONSHIPS}
        selected={MAP_NODES[0]}
        labelledBy="sample-map-heading"
      />
    </div>
  )
}

const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'

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

describe('FR-20 / NFR-17: the diagram’s lines and shapes are decoration beside words (D-132)', () => {
  it('hides every SVG from assistive technology, with nothing focusable and no text inside, and names each node in words', () => {
    const { container } = render(
      <MemoryRouter>
        <SampleMap />
      </MemoryRouter>,
    )

    // The lines' layer, the four legend shapes and their sample line, and a shape per node.
    const drawings = [...container.querySelectorAll('svg')]
    expect(container.querySelectorAll('svg.knowledge-map__lines')).toHaveLength(1)
    expect(container.querySelectorAll('svg.knowledge-map__lines line')).toHaveLength(MAP_RELATIONSHIPS.length)
    expect(drawings.length).toBe(1 + 4 + 1 + MAP_NODES.length)
    for (const svg of drawings) {
      expect(svg.getAttribute('aria-hidden')).toBe('true')
      expect(svg.getAttribute('focusable')).toBe('false')
      expect(svg.querySelectorAll(FOCUSABLE)).toHaveLength(0)
      expect(svg.querySelectorAll('[tabindex]')).toHaveLength(0)
      // Nothing to read is lost with it: no label or count is drawn in the SVG.
      expect(svg.textContent).toBe('')
    }

    // What the shapes and lines say to the eye is said in words. A node: its type,
    // its label, its count, and for the selected one that it is and what a second
    // selection does.
    const diagram = screen.getByRole('region', { name: TEXT.mapDiagramHeading })
    expect(
      within(diagram)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual([
      `${TEXT.mapTypeContributor}: Jane Doe, ${TEXT.mapConnectionsShown(2)}`,
      `${TEXT.mapTypeDocument}: Leave policy 2026, ${TEXT.mapConnectionsShown(2)}, ${TEXT.mapSelectedMark}. ${TEXT.mapSelectAgainDocument}`,
      `${TEXT.mapTypeMeeting}: Q3 planning sync, ${TEXT.mapConnectionsShown(1)}`,
      `${TEXT.mapTypeTag}: ${TEXT.mapTagLabel('Topic', 'people')}, ${TEXT.mapConnectionsShown(1)}`,
    ])
    expect(within(diagram).getByRole('link', { current: true }).textContent).toContain('Leave policy 2026')
    // The legend: each shape beside its word, and the line's meaning as a sentence.
    const legend = screen.getByRole('region', { name: TEXT.mapLegendHeading })
    expect(
      within(legend)
        .getAllByRole('listitem')
        .map((entry) => entry.textContent),
    ).toEqual([TEXT.mapTypeDocument, TEXT.mapTypeMeeting, TEXT.mapTypeTag, TEXT.mapTypeContributor])
    expect(within(legend).getByText(TEXT.mapLegendLine)).toBeTruthy()
  })

  it('sets no colour as an SVG attribute or an inline style: every colour is a class the contrast sweep reads', () => {
    const { container } = render(
      <MemoryRouter>
        <SampleMap />
      </MemoryRouter>,
    )

    // Presentation attributes that take a colour. tests/contrast.test.js and
    // tests/stylesheets.test.js read the stylesheets, so a colour written here
    // would be seen by neither.
    expect(
      [...container.querySelectorAll('[fill], [stroke], [color], [stop-color], [flood-color], [lighting-color]')].map(
        (element) => element.outerHTML.slice(0, 80),
      ),
    ).toEqual([])
    // Every shape and line gets its colour from a class instead.
    const shapes = container.querySelectorAll('svg rect, svg circle, svg polygon, svg line')
    expect(shapes.length).toBe(4 + 1 + MAP_NODES.length + MAP_RELATIONSHIPS.length)
    for (const shape of shapes) {
      expect(shape.getAttribute('class')).toMatch(/^knowledge-map__/)
    }
    // Inline style is position only: where a node sits on the grid, and the grid's tracks.
    const styled = [...container.querySelectorAll('[style]')]
    expect(styled.length).toBeGreaterThan(0)
    for (const element of styled) {
      const properties = element
        .getAttribute('style')
        .split(';')
        .map((declaration) => declaration.split(':')[0].trim())
        .filter(Boolean)
      for (const property of properties) {
        expect(property, element.outerHTML.slice(0, 80)).toMatch(/^grid-(column|row|template-columns)$/)
      }
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
          <SampleMap />
        </div>
      </MemoryRouter>,
    )
    // Both shapes of the failure: a focusable element inside aria-hidden
    // decoration, and decoration that is itself made focusable.
    const offenders = [...document.querySelectorAll(FOCUSABLE)].filter(
      (el) => el.closest('[aria-hidden="true"]') !== null,
    )
    expect(offenders.map((el) => el.outerHTML.slice(0, 60))).toEqual([])
    // The sweep saw the diagram: its links are there to be caught, and none was.
    expect(document.querySelectorAll('.knowledge-map__node').length).toBeGreaterThan(0)
  })
})
