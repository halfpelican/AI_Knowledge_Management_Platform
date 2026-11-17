import { useState } from 'react'
import './Avatar.css'

/**
 * The one address a user's picture may have (AVA-1): the contract's, a path on this
 * origin, `/api/users/{id}/picture`, with an optional query such as `?v=…`
 * (docs/api-contract.md, "Profile pictures"; apps/api/serializers.py picture_url). The id
 * is a run of letters, digits, `-` and `_`, so no `.`, `%` or `/` can turn the path into
 * another. Another scheme, another origin or another path is not used as an address.
 */
const PICTURE_ADDRESS = /^\/api\/users\/[A-Za-z0-9_-]+\/picture(?:\?[^#\s]*)?$/

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

/** The classes of an avatar in `state`, 'image' or 'initials', at `size`, with the caller's own. */
function avatarClasses(size, state, ...extra) {
  return ['avatar', size ? `avatar--${size}` : '', `avatar--${state}`, ...extra].filter(Boolean).join(' ')
}

/**
 * The picture itself, drawn as the Avatar draws it, from an address the caller vouches
 * for. Its one other caller is the component sheet, whose sample is the site's own icon,
 * because a user's picture needs a session. A user's picture never comes here directly:
 * it goes through Avatar, which checks its address first (AVA-1), and
 * tests/avatars.test.jsx fails if any other module imports this.
 */
export function AvatarPicture({ src, label = '', size = 'small', className = '', onError }) {
  return (
    <img
      className={avatarClasses(size, 'image', className)}
      src={src}
      alt={label}
      loading="lazy"
      decoding="async"
      onError={onError}
    />
  )
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
 * **Only the contract's address is used (AVA-1).** The server builds every `picture`
 * from the row's id alone, so nothing a user types reaches it today. Should that ever
 * change, any other address, a `javascript:` one, another origin's or another path on
 * this one, shows the initials: the browser never fetches it, and no other site
 * learns who is looking at the page.
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
  const usable = typeof picture === 'string' && PICTURE_ADDRESS.test(picture) && picture !== failed

  if (usable) {
    return (
      <AvatarPicture
        src={picture}
        label={label}
        size={size}
        className={[className, imageClassName].filter(Boolean).join(' ')}
        onError={() => setFailed(picture)}
      />
    )
  }

  const named = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': 'true' }
  return <span className={avatarClasses(size, 'initials', className, initialsClassName)} data-initials={initialsOf(name)} {...named} />
}
