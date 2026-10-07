import { useId } from 'react'
import { TEXT } from '../constants.js'
import Button from './Button.jsx'
import './Browse.css'

/*
 * FR-15's browsing controls: a facet group per dimension, the list of active
 * filters, and the sortable column heading. Pure views. Each reports a choice
 * to its caller and holds no filter state of its own, because the repository
 * keeps every filter and the sort in the address (D-61's gap 3: state held only
 * in a component is gone after a link and Back).
 *
 * None of them filters anything. The values, the counts and the list all arrive
 * already scoped to the caller's role (CLAUDE.md §6, invariant 1), and these
 * render exactly what they are given.
 */

/**
 * One browse dimension — Department, Project, Process or Topic — as a list of
 * toggle buttons, each a value with its count.
 *
 * A toggle button and not a link, so that one control both chooses a value and
 * takes it away again, and says which it will do: `aria-pressed` is announced,
 * and the pressed value carries a visible tick as well as its colour (WCAG 2.1
 * SC 1.4.1). One value per dimension (D-72), so choosing another replaces it.
 *
 * The count is the server's: documents in the caller's scope matching every
 * other active filter and this value (D-72). It is shown as a number with its
 * noun given to assistive technology, so the button's name reads "Finance 3
 * documents" rather than "Finance 3".
 *
 * @param {object} props
 * @param {string} props.heading
 * @param {{value: string, count: number}[]} props.values
 * @param {string} props.selected The value applied in this dimension, or ''.
 * @param {(value: string) => void} props.onChoose Called with '' to remove it.
 */
export function FacetGroup({ heading, values, selected, onChoose }) {
  const headingId = useId()
  return (
    <section className="facet-group" aria-labelledby={headingId}>
      <h3 id={headingId} className="facet-group__heading">
        {heading}
      </h3>
      {values.length === 0 ? (
        <p className="facet-group__empty">{TEXT.repositoryFacetEmpty}</p>
      ) : (
        <ul className="facet-group__list">
          {values.map(({ value, count }) => {
            const pressed = value === selected
            return (
              <li key={value}>
                <button
                  type="button"
                  className="facet"
                  aria-pressed={pressed}
                  onClick={() => onChoose(pressed ? '' : value)}
                >
                  {pressed ? (
                    <span className="facet__tick" aria-hidden="true">
                      ✓
                    </span>
                  ) : null}
                  <span className="facet__value">{value}</span>{' '}
                  <span className="facet__count" aria-hidden="true">
                    {count}
                  </span>
                  <span className="visually-hidden">{TEXT.repositoryFacetCount(count)}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/**
 * The filters in force, each with a way to remove it, and "Clear filters".
 *
 * The caller passes the filters it read from the address, never from a reply:
 * a 204 has no body, so on the one screen where knowing the active filters
 * matters most there is no reply to read them from (D-72).
 *
 * @param {object} props
 * @param {{key: string, name: string, value: string}[]} props.filters
 * @param {(key: string) => void} props.onRemove
 * @param {() => void} props.onClear
 */
export function ActiveFilterList({ filters, onRemove, onClear }) {
  const headingId = useId()
  if (filters.length === 0) return null
  return (
    <section className="active-filters" aria-labelledby={headingId}>
      <h2 id={headingId} className="active-filters__heading">
        {TEXT.repositoryActiveFilters}
      </h2>
      <ul className="active-filters__list">
        {filters.map((filter) => (
          <li key={filter.key} className="active-filters__item">
            <span>
              {filter.name}: <strong className="active-filters__value">{filter.value}</strong>
            </span>
            <Button
              variant="secondary"
              className="active-filters__remove"
              aria-label={TEXT.repositoryRemoveFilterLabel(filter.name, filter.value)}
              onClick={() => onRemove(filter.key)}
            >
              {TEXT.repositoryRemoveFilter}
            </Button>
          </li>
        ))}
      </ul>
      <Button variant="secondary" onClick={onClear}>
        {TEXT.repositoryClearFilters}
      </Button>
    </section>
  )
}

/** The direction `sort` holds for `field`: 'ascending', 'descending', or null. */
function sortDirection(sort, field) {
  if (sort === field) return 'ascending'
  if (sort === `-${field}`) return 'descending'
  return null
}

/**
 * A column heading that is also its sort control (FR-15: "with sorting").
 *
 * The heading carries `aria-sort` for the column in force, and the button names
 * the direction in words as well as with an arrow, so the order is not conveyed
 * by a glyph alone (WCAG 2.1 SC 1.1.1). The first press sorts ascending; a press
 * on the column already in force reverses it.
 *
 * @param {object} props
 * @param {string} props.label
 * @param {string} props.field The contract's `sort` field.
 * @param {string} props.sort The sort in force, e.g. '-uploaded_at'.
 * @param {(sort: string) => void} props.onSort
 */
export function SortHeader({ label, field, sort, onSort }) {
  const direction = sortDirection(sort, field)
  const next = direction === 'ascending' ? `-${field}` : field
  return (
    <th scope="col" aria-sort={direction ?? undefined} className="sort-header">
      <button type="button" className="sort-header__button" onClick={() => onSort(next)}>
        {label}
        {direction ? (
          <>
            <span className="visually-hidden">
              , {direction === 'ascending' ? TEXT.repositorySortedAscending : TEXT.repositorySortedDescending}
            </span>
            <span className="sort-header__arrow" aria-hidden="true">
              {direction === 'ascending' ? '▲' : '▼'}
            </span>
          </>
        ) : null}
      </button>
    </th>
  )
}
