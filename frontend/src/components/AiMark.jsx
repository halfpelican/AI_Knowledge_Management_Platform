import { TEXT } from '../constants.js'
import './AiMark.css'

/**
 * NFR-15's mark: "All AI-generated content (summaries, action items, extracted
 * knowledge) must be visually distinguished from human-authored content using one
 * consistent convention, such as an AI-generated badge, applied system-wide."
 *
 * **The convention is FR-10's, and there is one of it.** FR-10 marked its type,
 * department and tags first (src/components/Classification.jsx), and this is that
 * mark for every surface since: FR-16's summary and its extracted action items,
 * and a passage of a meeting's summary where FR-12 shows a source passage or a
 * search snippet. It has two parts, and each is defined once:
 *
 * - **The words "Suggested by AI"**, beside the content. They are the mark. A
 *   colour or a border is not one to a screen reader, nor to anyone who cannot
 *   tell a dashed line from a solid one (WCAG 2.1 SC 1.4.1). FR-10's entries in
 *   src/constants.js and this component read the same constant, so the two cannot
 *   come to say it differently.
 * - **A dashed boundary** round what the AI wrote, where a person's is solid: a
 *   second cue, never the only one. Its style is the token `--border-style-ai`,
 *   which FR-10's `.tag--ai`, the citation's `.citation-panel__passage--ai` and
 *   the `ai-content` class in AiMark.css all read.
 *
 * Once a person has changed an extracted item the mark says so, "Suggested by AI,
 * edited by a person", as FR-10's says "confirmed by a person": the content is no
 * longer the AI's alone, and it is still not a person's from the start.
 *
 * The mark is said from a field of the reply (`origin`, `edited`, `ai_generated`,
 * `snippet_ai_generated`, or the summary itself, which is AI content by what it
 * is) and never worked out from the text it marks.
 *
 * @param {object} props
 * @param {boolean} [props.edited] A person has changed this AI content.
 * @param {string} [props.id] So a region can be described by its mark.
 * @param {string} [props.className]
 */
export default function AiMark({ edited = false, id, className = '' }) {
  return (
    <span id={id} className={['ai-mark', className].filter(Boolean).join(' ')}>
      {edited ? TEXT.aiSuggestedEdited : TEXT.aiSuggested}
    </span>
  )
}

/**
 * What the same convention says of content a person wrote: "Added by a person",
 * FR-10's words for a tag a person applied. It carries no AI mark, and its
 * boundary (`person-content`) is solid.
 */
export function PersonMark({ className = '' }) {
  return <span className={['person-mark', className].filter(Boolean).join(' ')}>{TEXT.addedByPerson}</span>
}
