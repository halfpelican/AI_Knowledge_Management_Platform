import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { listRoles, listUsers, unlockUser, updateUserRole } from '../api/users.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Dialog from '../components/Dialog.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import Notice from '../components/Notice.jsx'
import SelectInput from '../components/SelectInput.jsx'
import { TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import './RoleManagement.css'

const dateFormat = new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium' })
// A lock lasts minutes, so its times are said as times of day.
const timeFormat = new Intl.DateTimeFormat('en-AU', { timeStyle: 'short' })

/**
 * The longest delay a timer takes. `setTimeout` fires at once for a longer one,
 * which for the redraw below would mean redrawing the table on every tick.
 */
const MAXIMUM_TIMEOUT_MS = 2 ** 31 - 1

function formatCreated(iso) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : dateFormat.format(date)
}

/** A timestamp from the API as a time of day, or '' where it is missing or unreadable. */
function formatTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : timeFormat.format(date)
}

/**
 * FR-03 (D-130): the user's lock while it lasts, or null. Null where `lock` is
 * null, where the list carries no `lock` (a requester without
 * release_account_locks is not told), where `locked_until` is unreadable, and
 * where it has passed, which reads as unlocked.
 */
function liveLock(user, now) {
  const lock = user?.lock
  if (!lock || typeof lock !== 'object') return null
  const until = Date.parse(lock.locked_until)
  return Number.isFinite(until) && until > now ? lock : null
}

/** When the soonest live lock among `users` ends, in milliseconds, or null where none is live. */
function soonestLockEnd(users, now) {
  let soonest = null
  for (const user of users) {
    const lock = liveLock(user, now)
    if (!lock) continue
    const until = Date.parse(lock.locked_until)
    if (soonest === null || until < soonest) soonest = until
  }
  return soonest
}

/**
 * FR-03's Account cell (D-130). A live lock reads "Locked until" its end, in a
 * bordered badge. Another user's lock has its Unlock button beside it; the
 * signed-in Administrator's own lock has a note instead, because FR-03 forbids
 * releasing a lock on one's own account. An account with no live lock reads
 * "Active", and one the list says nothing about (no `lock` key) reads nothing,
 * because the screen was not told.
 */
function AccountState({ user, now, own, onUnlock }) {
  const lock = liveLock(user, now)
  if (!lock) {
    return 'lock' in user ? <span className="roles-table__active">{TEXT.accountActive}</span> : null
  }
  return (
    <div className="roles-table__lock">
      <span className="roles-table__badge">{TEXT.accountLockedUntil(formatTime(lock.locked_until))}</span>
      {own ? (
        <p className="roles-table__note">{TEXT.accountLockedOwn}</p>
      ) : (
        <Button variant="secondary" aria-label={TEXT.unlockLabel(user.name)} onClick={() => onUnlock(user)}>
          {TEXT.unlock}
        </Button>
      )}
    </div>
  )
}

/**
 * The confirmation dialogue's body for releasing `user`'s lock: when the lock
 * began and from which address, where the lockout was recorded, and when it ends;
 * that the password is not changed (FR-03); and the check the security review asks
 * for before the press (finding L3).
 */
function UnlockDetails({ user }) {
  const lock = user.lock ?? {}
  const sourceIp = typeof lock.source_ip === 'string' ? lock.source_ip : ''
  return (
    <>
      <p>{TEXT.unlockLockDetails(formatTime(lock.locked_at), sourceIp, formatTime(lock.locked_until))}</p>
      <p>{TEXT.unlockPasswordUnchanged}</p>
      <p>{TEXT.unlockCheckRequest(user.name)}</p>
    </>
  )
}

/**
 * The user table as a pure view.
 *
 * The API returns a user's role as its name and takes a role change as a
 * `role_id` (FR-05, D-25), so the select's values are role ids and the two maps
 * below cross between the two. `selected` maps user id to the role id currently
 * chosen in that row; a row's Save button is enabled only when the choice
 * differs from the saved role. `savingId` is the id of the row whose PATCH is in
 * flight.
 *
 * FR-03's Account column reads each user's `lock` against `now` (milliseconds).
 * `currentUserId` is the signed-in Administrator, whose own row offers no Unlock
 * button; `onUnlock` opens the confirmation for another user's.
 */
export function RoleTable({
  users,
  roles,
  selected,
  savingId,
  currentUserId = null,
  now,
  onSelect,
  onSave,
  onUnlock,
}) {
  const options = roles.map((role) => ({ value: role.role_id, label: role.name }))
  const roleIdByName = new Map(roles.map((role) => [role.name, role.role_id]))

  if (users.length === 0) {
    return <Notice variant="info">{TEXT.noUsers}</Notice>
  }

  return (
    <div className="table-scroll" role="region" aria-labelledby="roles-heading" tabIndex={0}>
      <table className="roles-table">
        <caption className="visually-hidden">Users, whether their accounts are locked, and their roles</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Email</th>
            <th scope="col">{TEXT.accountColumn}</th>
            <th scope="col">Role</th>
            <th scope="col">Created</th>
            <th scope="col">
              <span className="visually-hidden">Action</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => {
            const savedRoleId = roleIdByName.get(user.role) ?? ''
            const choice = selected[user.id] ?? savedRoleId
            const changed = choice !== '' && choice !== savedRoleId
            const saving = savingId === user.id
            return (
              <tr key={user.id}>
                <th scope="row">{user.name}</th>
                <td className="roles-table__email">{user.email}</td>
                <td className="roles-table__account">
                  <AccountState
                    user={user}
                    now={now}
                    own={currentUserId !== null && user.id === currentUserId}
                    onUnlock={onUnlock}
                  />
                </td>
                <td className="roles-table__role">
                  <SelectInput
                    id={`role-${user.id}`}
                    label={`Role for ${user.name}`}
                    labelHidden
                    className="select-field--inline"
                    options={options}
                    value={choice}
                    disabled={saving}
                    onChange={(event) => onSelect(user.id, event.target.value)}
                  />
                </td>
                <td className="roles-table__created">
                  <time dateTime={user.created_at}>{formatCreated(user.created_at)}</time>
                </td>
                <td>
                  <Button
                    variant="secondary"
                    disabled={!changed || saving}
                    aria-label={`Save role for ${user.name}`}
                    onClick={() => onSave(user)}
                  >
                    {saving ? 'Saving…' : 'Save'}
                  </Button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/**
 * FR-05 role management (Administrator), and FR-03's release of a lock.
 *
 * Reads GET /api/users and GET /api/roles, confirms the change in a modal
 * dialogue — "Confirmation dialogue is shown before the role change is applied"
 * — and then saves the row with PATCH /api/users/{id}/role carrying `role_id`.
 * The table updates from the response, so it reflects what the server actually
 * stored rather than what was asked for. The PATCH reply is the plain user
 * object, with no `lock`, so it is merged into the row rather than replacing it:
 * a locked account keeps its lock, and its Unlock button, through a role change
 * (the security review, Q5).
 *
 * FR-03 (D-130): a locked account's row says until when, and offers Unlock on
 * every row but the signed-in Administrator's own. Unlock opens a confirmation
 * first and sends nothing until it is confirmed; then POST /api/users/{id}/unlock,
 * and the row is replaced from the 200. A 409 (no longer locked) or a 404 (no
 * such user) says so and reads the list again.
 *
 * The screen is admin-only, and the route that reaches it is guarded by
 * RequireRole, which sends everyone else to /403 (FR-06). That is usability. The
 * server is the authority: a 403 on the list renders the not-permitted notice
 * and nothing else (CLAUDE.md §6, invariant 4).
 */
export default function RoleManagement() {
  useDocumentTitle('Role management')
  const { user: currentUser, refresh } = useAuth()
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [selected, setSelected] = useState({})
  const [savingId, setSavingId] = useState(null)
  const [notice, setNotice] = useState(null)
  // The pending change, held while the confirmation dialogue is open.
  const [pending, setPending] = useState(null)
  // FR-03: the user whose lock is about to be released, held while its
  // confirmation is open, and whether that release is in flight.
  const [pendingUnlock, setPendingUnlock] = useState(null)
  const [unlocking, setUnlocking] = useState(false)
  // Bumping this re-runs the load effect (retry, or a 404 that means the list is stale).
  const [reloadKey, setReloadKey] = useState(0)
  // FR-03: the clock the Account column reads each lock against. It is set when the
  // list arrives and moved on when the soonest lock ends, which is the only moment a
  // row can change from locked to unlocked, so a lock that has passed reads as
  // unlocked at once rather than at whatever redraws the table next.
  const [now, setNow] = useState(() => Date.now())
  // Where focus goes when the dialogue closes and the button that opened it has
  // become disabled, which is what happens after a successful save.
  const headingRef = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    async function load() {
      let result = null
      let failure = null
      try {
        const [userList, roleList] = await Promise.all([listUsers({ signal }), listRoles({ signal })])
        result = { users: userList ?? [], roles: roleList ?? [] }
      } catch (error) {
        if (error?.name === 'AbortError') return
        failure =
          error instanceof ApiError
            ? error
            : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
      }
      if (signal.aborted) return
      if (result) {
        setUsers(result.users)
        setRoles(result.roles)
        setSelected({})
        setNow(Date.now())
      }
      setLoadError(failure)
      setLoading(false)
    }
    load()
    return () => controller.abort()
  }, [reloadKey])

  // One timer, for the soonest lock to end. It re-runs when `now` moves, which is
  // when that timer has fired, so the next lock's end is scheduled in turn.
  useEffect(() => {
    const soonest = soonestLockEnd(users, Date.now())
    if (soonest === null) return undefined
    const timer = setTimeout(() => setNow(Date.now()), Math.min(soonest - Date.now() + 1, MAXIMUM_TIMEOUT_MS))
    return () => clearTimeout(timer)
  }, [users, now])

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])

  function handleRetry() {
    setLoading(true)
    setLoadError(null)
    reload()
  }

  function handleSelect(userId, roleId) {
    setSelected((current) => ({ ...current, [userId]: roleId }))
  }

  /** Opens the confirmation dialogue. Nothing is sent until it is confirmed. */
  function handleSave(target) {
    const roleId = selected[target.id]
    const role = roles.find((candidate) => candidate.role_id === roleId)
    if (!roleId || !role || role.name === target.role) return
    setNotice(null)
    setPending({ user: target, roleId, roleName: role.name })
  }

  function handleCancel() {
    if (savingId) return
    setPending(null)
  }

  async function handleConfirm() {
    if (!pending) return
    const { user: target, roleId } = pending
    setSavingId(target.id)
    try {
      const updated = await updateUserRole(target.id, roleId)
      // Merged, not replaced: the reply carries no `lock`, and the row keeps its own.
      setUsers((current) => current.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)))
      setSelected((current) => {
        const next = { ...current }
        delete next[target.id]
        return next
      })
      setNotice({ variant: 'info', title: 'Role saved', text: TEXT.roleSaved(updated.name, updated.role) })
      // Roles are read per request on the server; if this was the signed-in
      // administrator, reload so the navigation and guards reflect it at once.
      if (currentUser && updated.id === currentUser.id) await refresh()
    } catch (error) {
      handleSaveError(error, target)
    } finally {
      setSavingId(null)
      setPending(null)
    }
  }

  function handleSaveError(error, target) {
    if (!(error instanceof ApiError)) {
      setNotice({ variant: 'error', title: 'Could not save', text: messageForStatus() })
      return
    }
    if (error.status === 403 && currentUser && target.id === currentUser.id) {
      // FR-05: "a user cannot remove their own administrator role". The server
      // refuses that with a 403, and the only 403 it can raise for a request
      // whose target is the requester is this one — the requester's permission
      // was checked on the same request.
      setNotice({ variant: 'error', title: 'Change refused', text: TEXT.roleChangeSelfDemotion })
      setSelected((current) => {
        const next = { ...current }
        delete next[target.id]
        return next
      })
      return
    }
    if (error.status === 403) {
      // The permission has gone since the list loaded. Fall back to the same
      // notice an Employee would see, and re-read who we are.
      setLoadError(error)
      refresh()
      return
    }
    if (error.status === 404) {
      // FR-05: "404 Not Found if user/role doesn't exist" — the list is stale.
      setNotice({ variant: 'error', title: 'Could not save', text: TEXT.roleChangeStale })
      reload()
      return
    }
    setNotice({ variant: 'error', title: 'Could not save', text: error.message })
  }

  /** FR-03: opens the confirmation for releasing `target`'s lock. Nothing is sent until it is confirmed. */
  function handleUnlock(target) {
    setNotice(null)
    setPendingUnlock({ user: target })
  }

  function handleUnlockCancel() {
    if (unlocking) return
    setPendingUnlock(null)
  }

  async function handleUnlockConfirm() {
    if (!pendingUnlock || unlocking) return
    const { user: target } = pendingUnlock
    setUnlocking(true)
    try {
      const updated = await unlockUser(target.id)
      // The row as the server now lists it, with `lock` null. Its Unlock button
      // goes with the dialogue, so focus moves to the heading.
      setUsers((current) => current.map((u) => (u.id === updated.id ? updated : u)))
      setNotice({ variant: 'info', title: TEXT.unlockedTitle, text: TEXT.accountUnlocked(updated.name) })
    } catch (error) {
      handleUnlockError(error, target)
    } finally {
      setUnlocking(false)
      setPendingUnlock(null)
    }
  }

  function handleUnlockError(error, target) {
    if (!(error instanceof ApiError)) {
      setNotice({ variant: 'error', title: TEXT.unlockFailedTitle, text: messageForStatus() })
      return
    }
    if (error.status === 409) {
      // FR-03's 409: the account is not locked. The lock ended, or another
      // administrator released it, since the list was read. The row says so at
      // once, which also takes its Unlock button away, and the list is read again.
      setUsers((current) => current.map((u) => (u.id === target.id ? { ...u, lock: null } : u)))
      setNotice({ variant: 'info', text: TEXT.unlockNotLocked })
      reload()
      return
    }
    if (error.status === 404) {
      // No such user: the list is stale. The row goes at once, and the list is read again.
      setUsers((current) => current.filter((u) => u.id !== target.id))
      setNotice({ variant: 'error', title: TEXT.unlockFailedTitle, text: TEXT.roleChangeStale })
      reload()
      return
    }
    if (error.status === 403 && currentUser && target.id === currentUser.id) {
      // FR-03: no Administrator may release a lock on their own account, and the
      // server refuses it with a 403 whether or not the account is locked. No button
      // is offered on the signed-in Administrator's own row, so this is reached only
      // if the screen's idea of who is signed in is out of date.
      setNotice({ variant: 'error', title: TEXT.unlockRefusedTitle, text: TEXT.unlockSelfRefused })
      return
    }
    if (error.status === 403) {
      // The permission has gone since the list loaded, as for a role change.
      setLoadError(error)
      refresh()
      return
    }
    setNotice({ variant: 'error', title: TEXT.unlockFailedTitle, text: error.message })
  }

  return (
    <RoleManagementView
      loading={loading}
      loadError={loadError}
      notice={notice}
      users={users}
      roles={roles}
      selected={selected}
      savingId={savingId}
      pending={pending}
      pendingUnlock={pendingUnlock}
      unlocking={unlocking}
      currentUserId={currentUser?.id ?? null}
      now={now}
      headingRef={headingRef}
      onSelect={handleSelect}
      onSave={handleSave}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
      onUnlock={handleUnlock}
      onUnlockConfirm={handleUnlockConfirm}
      onUnlockCancel={handleUnlockCancel}
      onRetry={handleRetry}
    />
  )
}

/**
 * Whole-screen view: loading, not-permitted (a 403 from the API), load error
 * with retry, or the table — plus the confirmation dialogue when a role change
 * or the release of a lock is pending.
 */
export function RoleManagementView({
  loading,
  loadError,
  notice,
  users,
  roles,
  selected,
  savingId,
  pending,
  pendingUnlock = null,
  unlocking = false,
  currentUserId = null,
  now,
  headingRef,
  onSelect,
  onSave,
  onConfirm,
  onCancel,
  onUnlock,
  onUnlockConfirm,
  onUnlockCancel,
  onRetry,
}) {
  let body
  if (loading) {
    body = <p role="status">{TEXT.loadingUsers}</p>
  } else if (loadError && loadError.status === 403) {
    body = <NotPermitted />
  } else if (loadError) {
    body = (
      <>
        <Notice variant="error" title="Could not load users">
          {loadError.message}
        </Notice>
        <div className="roles-page__actions">
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      </>
    )
  } else {
    body = (
      <>
        {notice ? (
          <Notice variant={notice.variant} title={notice.title}>
            {notice.text}
          </Notice>
        ) : null}
        <RoleTable
          users={users}
          roles={roles}
          selected={selected}
          savingId={savingId}
          currentUserId={currentUserId}
          now={now}
          onSelect={onSelect}
          onSave={onSave}
          onUnlock={onUnlock}
        />
      </>
    )
  }

  let dialog = null
  if (pending) {
    dialog = (
      <Dialog
        title={TEXT.roleChangeConfirm(pending.user.name, pending.roleName)}
        confirmLabel="Change role"
        busyLabel="Changing…"
        cancelLabel="Cancel"
        busy={Boolean(savingId)}
        returnFocusRef={headingRef}
        onConfirm={onConfirm}
        onCancel={onCancel}
      >
        <p>
          {pending.user.name} ({pending.user.email}) currently has the {pending.user.role} role. The
          change takes effect on their next request and is recorded in the audit log.
        </p>
      </Dialog>
    )
  } else if (pendingUnlock) {
    dialog = (
      <Dialog
        title={TEXT.unlockConfirm(pendingUnlock.user.name)}
        confirmLabel={TEXT.unlockConfirmLabel}
        busyLabel={TEXT.unlocking}
        cancelLabel={TEXT.unlockCancel}
        busy={unlocking}
        returnFocusRef={headingRef}
        onConfirm={onUnlockConfirm}
        onCancel={onUnlockCancel}
      >
        <UnlockDetails user={pendingUnlock.user} />
      </Dialog>
    )
  }

  return (
    <div className="roles-page">
      <h1 id="roles-heading" ref={headingRef} tabIndex={-1}>
        Role management
      </h1>
      <p>{TEXT.rolesIntro}</p>
      {body}
      {dialog}
    </div>
  )
}
