import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TEXT } from '../constants.js'
import { searchTermError } from '../utils/validation.js'
import Button from './Button.jsx'
import TextInput from './TextInput.jsx'
import './SearchField.css'

/**
 * FR-12's search field, which the requirement says is "available from every
 * page".
 *
 * One component in two places: the application header, where it is the field on
 * every page, and the search screen itself, where it is the field that refines
 * the term already searched for. Both submit to `/search?q=`, so there is one
 * route into results and one definition of what happens when the term is too
 * short.
 *
 * The refusal is FR-12's own: "queries shorter than two characters are rejected
 * client-side", and the message names the minimum so the user is told what would
 * be accepted. The server enforces it too and answers 400 (`docs/api-contract.md`,
 * CLAUDE.md §6 invariant 4); this only decides what happens before a request.
 *
 * `role="search"` makes it a landmark, so a screen-reader user can jump to it
 * from anywhere without hunting through the navigation.
 *
 * @param {object} props
 * @param {string} props.id Distinct per instance: two fields on one page cannot share ids.
 * @param {string} [props.initialTerm] The term the screen was rendered for.
 * @param {string} [props.hint] Rendered under the field where there is room for it.
 * @param {string} [props.className]
 */
export default function SearchField({ id, initialTerm = '', hint, className = '' }) {
  const navigate = useNavigate()
  const [term, setTerm] = useState(initialTerm)
  const [lastTermFromUrl, setLastTermFromUrl] = useState(initialTerm)
  const [error, setError] = useState(null)

  // Follows the URL: searching from the header while this screen is open leaves
  // the field showing what the results below it are for.
  //
  // Adjusted during render rather than in an effect, which is React's own pattern
  // for a state that has to follow a prop: the component re-renders immediately
  // with the new value and the browser never paints the stale one. The comparison
  // is against the last value seen from the URL, so it fires once per navigation
  // and never fights what is being typed. Remounting with a `key` would do the
  // same thing and would throw focus off the field the user had just submitted
  // from, which is the regression this avoids.
  if (initialTerm !== lastTermFromUrl) {
    setLastTermFromUrl(initialTerm)
    setTerm(initialTerm)
    if (error) setError(null)
  }

  function handleSubmit(event) {
    event.preventDefault()
    // The term is checked as typed, never trimmed: the server matches and logs it
    // character for character (src/utils/validation.js).
    const refusal = searchTermError(term)
    setError(refusal)
    if (refusal) return
    navigate(`/search?q=${encodeURIComponent(term)}`)
  }

  return (
    <form
      role="search"
      aria-label={TEXT.searchNavLabel}
      className={['search-field', className].filter(Boolean).join(' ')}
      onSubmit={handleSubmit}
      noValidate
    >
      {/* The submit control goes in TextInput's `action` slot, which puts it in
          the same row as the input and after it in the DOM: the tab order is
          label, field, button, exactly as the password toggle's is. */}
      <TextInput
        id={id}
        label={TEXT.searchFieldLabel}
        hint={hint}
        error={error}
        type="search"
        name="q"
        value={term}
        className="search-field__input"
        action={
          <Button type="submit" variant="secondary" className="search-field__submit">
            {TEXT.searchSubmit}
          </Button>
        }
        onChange={(event) => {
          setTerm(event.target.value)
          if (error) setError(null)
        }}
      />
    </form>
  )
}
