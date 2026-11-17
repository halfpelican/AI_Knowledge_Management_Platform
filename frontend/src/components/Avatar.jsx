import { useState } from 'react'
import './Avatar.css'

/** Up to two initials: the first letter of the first word and of the last, in capitals. */
function initialsOf(name) {
  const words = String(name ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (words.length === 0) return ''
  // Code points, so a name that begins with a character outside the BMP is not cut in half.
  const first = Array.from(words[0])[0]
  const last = words.length > 1 ? Array.from(words[words.length - 1])[0] : ''
  return `${first}${last}`.toLocaleUpperCase()
}

/**
 * A person's profile picture, or their initials where they have none (D-137:
 * every signed-in user sees pictures wherever users are listed: the header, role
 * management and the attendee lists).
 *
 * `picture` is the user object's own field, the address of
 * `GET /api/users/{id}/picture?v=…`, or null. The browser fetches it as an image
 * with the session cookie, as it follows FR-15's download link. A replaced picture
 * has a new `v`, so a new address. If the image cannot be loaded, the initials take
 * its place, and a new address is tried again.
 *
 * **Decorative by default.** Everywhere it is used the person's name is shown beside
 * it, so the picture adds nothing a screen reader needs: `alt=""`, and the initials
 * `aria-hidden`. Pass `label` only where no name is beside it, and the picture is
 * then named by it.
 *
 * **The initials are painted by the stylesheet** (`content: attr(data-initials)` in
 * Avatar.css), not written into the page. They are decoration either way, and this
 * keeps the text of whatever holds the avatar its own: a role table's row header
 * reads as the person's name alone, and the navigation's link as "Profile".
 *
 * `size` picks a size class from Avatar.css; `null` leaves the size to the caller's
 * classes, as #119's large picture on the Profile page sets its own.
 * `imageClassName` and `initialsClassName` are added to the one element that is
 * rendered in each state.
 */
export default function Avatar({
  name,
  picture,
  label = '',
  size = 'small',
  className = '',
  imageClassName = '',
  initialsClassName = '',
}) {
  // The address that failed to load: a new address is tried, this one is not again.
  const [failed, setFailed] = useState(null)
  const usable = typeof picture === 'string' && picture !== '' && picture !== failed

  function classes(state, extra) {
    return ['avatar', size ? `avatar--${size}` : '', `avatar--${state}`, className, extra].filter(Boolean).join(' ')
  }

  if (usable) {
    return (
      <img
        className={classes('image', imageClassName)}
        src={picture}
        alt={label}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(picture)}
      />
    )
  }

  const named = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': 'true' }
  return <span className={classes('initials', initialsClassName)} data-initials={initialsOf(name)} {...named} />
}
