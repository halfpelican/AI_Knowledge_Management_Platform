import { useCallback, useEffect, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { listRoles, listUsers, updateUserRole } from '../api/users.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
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
 * `selected` maps user id to the role currently chosen in that row; a row's
 * Save button is enabled only when the choice differs from the saved role.
 * `savingId` is the id of the row whose PATCH is in flight.
 */
export function RoleTable({ users, roles, selected, savingId, onSelect, onSave }) {
  const options = roles.map((role) => ({ value: role.name, label: role.name }))

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
            const choice = selected[user.id] ?? user.role
            const changed = choice !== user.role
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
 * Reads GET /api/users and GET /api/roles, and saves a row with
 * PATCH /api/users/{id}/role. The server is the authority: a 403 on any call
 * renders the not-permitted notice, and if the administrator changes their own
 * role the signed-in user is reloaded so the interface follows.
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
  // Bumping this re-runs the load effect (retry, or a 404 that means the list is stale).
  const [reloadKey, setReloadKey] = useState(0)

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

  function handleSelect(userId, role) {
    setSelected((current) => ({ ...current, [userId]: role }))
  }

  async function handleSave(target) {
    const role = selected[target.id]
    if (!role || role === target.role) return
    setSavingId(target.id)
    setNotice(null)
    try {
      const updated = await updateUserRole(target.id, role)
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
      if (error instanceof ApiError && error.status === 403) {
        setLoadError(error)
        await refresh()
      } else if (error instanceof ApiError && error.status === 404) {
        setNotice({ variant: 'error', title: 'Could not save', text: error.message })
        reload()
      } else {
        setNotice({
          variant: 'error',
          title: 'Could not save',
          text: error instanceof ApiError ? error.message : messageForStatus(),
        })
      }
    } finally {
      setSavingId(null)
    }
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
      onSelect={handleSelect}
      onSave={handleSave}
      onRetry={handleRetry}
    />
  )
}

/** Whole-screen view: loading, not-permitted (403), load error with retry, or the table. */
export function RoleManagementView({
  loading,
  loadError,
  notice,
  users,
  roles,
  selected,
  savingId,
  onSelect,
  onSave,
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
      <h1 id="roles-heading">Role management</h1>
      <p>
        Choose a role for a user and save the row. Changes take effect on that user&apos;s next request and are
        recorded in the audit log.
      </p>
      {body}
    </div>
  )
}
