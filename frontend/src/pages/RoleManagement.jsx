import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { listRoles, listUsers, updateUserRole } from '../api/users.js'
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

function formatCreated(iso) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : dateFormat.format(date)
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
 */
export function RoleTable({ users, roles, selected, savingId, onSelect, onSave }) {
  const options = roles.map((role) => ({ value: role.role_id, label: role.name }))
  const roleIdByName = new Map(roles.map((role) => [role.name, role.role_id]))

  if (users.length === 0) {
    return <Notice variant="info">{TEXT.noUsers}</Notice>
  }

  return (
    <div className="table-scroll" role="region" aria-labelledby="roles-heading" tabIndex={0}>
      <table className="roles-table">
        <caption className="visually-hidden">Users and their roles</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Email</th>
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
 * FR-05 role management (Administrator).
 *
 * Reads GET /api/users and GET /api/roles, confirms the change in a modal
 * dialogue — "Confirmation dialogue is shown before the role change is applied"
 * — and then saves the row with PATCH /api/users/{id}/role carrying `role_id`.
 * The table updates from the response, so it reflects what the server actually
 * stored rather than what was asked for.
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
  // Bumping this re-runs the load effect (retry, or a 404 that means the list is stale).
  const [reloadKey, setReloadKey] = useState(0)
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
      }
      setLoadError(failure)
      setLoading(false)
    }
    load()
    return () => controller.abort()
  }, [reloadKey])

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
      setUsers((current) => current.map((u) => (u.id === updated.id ? updated : u)))
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
      headingRef={headingRef}
      onSelect={handleSelect}
      onSave={handleSave}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
      onRetry={handleRetry}
    />
  )
}

/**
 * Whole-screen view: loading, not-permitted (a 403 from the API), load error
 * with retry, or the table — plus the confirmation dialogue when a change is
 * pending.
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
  headingRef,
  onSelect,
  onSave,
  onConfirm,
  onCancel,
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
          onSelect={onSelect}
          onSave={onSave}
        />
      </>
    )
  }

  return (
    <div className="roles-page">
      <h1 id="roles-heading" ref={headingRef} tabIndex={-1}>
        Role management
      </h1>
      <p>
        Choose a role for a user and save the row. Changes take effect on that user&apos;s next request and are
        recorded in the audit log.
      </p>
      {body}
      {pending ? (
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
      ) : null}
    </div>
  )
}
