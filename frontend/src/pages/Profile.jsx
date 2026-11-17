import { useEffect, useId, useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError, messageForStatus } from '../api/client.js'
import { changePassword, PICTURE_BUSY_CODE, removeProfilePicture, uploadProfilePicture } from '../api/profile.js'
import useAuth from '../auth/useAuth.js'
import Avatar from '../components/Avatar.jsx'
import Button from '../components/Button.jsx'
import Dialog from '../components/Dialog.jsx'
import Notice from '../components/Notice.jsx'
import PasswordRequirements from '../components/PasswordRequirements.jsx'
import TextInput from '../components/TextInput.jsx'
import { MAX_PICTURE_BYTES, PICTURE_EXTENSIONS, PICTURE_TYPES, PROFILE_TEXT, ROLES, VALIDATION } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { passwordMeetsPolicy } from '../utils/password.js'
import { whenToRetry } from '../utils/retryAfter.js'
import './Profile.css'

const EMPTY_PASSWORDS = { currentPassword: '', newPassword: '', confirmPassword: '' }

/** The fields the change's 400 names, and the form's field each one's messages go under. */
const SERVER_FIELDS = { current_password: 'currentPassword', new_password: 'newPassword' }

/**
 * FR-01's client-side checks, as registration applies them (src/utils/validation.js,
 * `validateRegistration`): every field required, the new password meeting the one
 * policy the server enforces too (src/utils/password.js), and the confirmation
 * matching it. An empty object means every check passed. The server decides
 * regardless (CLAUDE.md §6, invariant 4), and refuses more: a new password like the
 * user's own name, say, or equal to the current one.
 */
function validatePasswordChange({ currentPassword, newPassword, confirmPassword }) {
  const errors = {}
  if (!currentPassword) errors.currentPassword = PROFILE_TEXT.currentPasswordRequired
  if (!newPassword) errors.newPassword = PROFILE_TEXT.newPasswordRequired
  else if (!passwordMeetsPolicy(newPassword)) errors.newPassword = VALIDATION.passwordRequirements
  if (!confirmPassword) errors.confirmPassword = PROFILE_TEXT.confirmNewPasswordRequired
  else if (confirmPassword !== newPassword) errors.confirmPassword = VALIDATION.passwordMismatch
  return errors
}

/**
 * Every message of each field a 400 names, under the form's own field names. The
 * validators' messages are written for the person typing, and are the one backend
 * text a form shows (src/utils/fieldErrors.js); every one is shown, since a new
 * password can fail several at once.
 */
function passwordFieldErrors(error) {
  const fieldErrors = {}
  const details = error instanceof ApiError && error.status === 400 ? error.details : null
  if (!details || typeof details !== 'object' || Array.isArray(details)) return fieldErrors
  for (const [serverField, field] of Object.entries(SERVER_FIELDS)) {
    const messages = details[serverField]
    if (Array.isArray(messages) && messages.length > 0 && messages.every((message) => typeof message === 'string')) {
      fieldErrors[field] = messages.join(' ')
    }
  }
  return fieldErrors
}

/** The form's banner for a change refused without naming a field. */
function passwordFailure(error) {
  if (!(error instanceof ApiError)) return messageForStatus()
  if (error.status === 429) return PROFILE_TEXT.passwordRateLimited(whenToRetry(error.retryAfter))
  return error.message
}

/**
 * Why the page will not send `file`, or null. A convenience, as FR-08's check is:
 * by the type the browser gives the file, or its extension where it gives none, and
 * its size. The server reads the format from the content and decides.
 */
function pictureRefusal(file) {
  const type = (file.type ?? '').toLowerCase()
  const name = (file.name ?? '').toLowerCase()
  const accepted = type ? PICTURE_TYPES.includes(type) : PICTURE_EXTENSIONS.some((extension) => name.endsWith(extension))
  if (!accepted) return PROFILE_TEXT.pictureTypeUnsupported
  if (file.size > MAX_PICTURE_BYTES) return PROFILE_TEXT.pictureTooLarge
  return null
}

/**
 * The notice for an upload the server refused, and never the reply's `detail`: the
 * contract's message for the 400, the 413s, the 415 and `picture_busy`, and the
 * page's own for the rate's 429, for which the contract gives DRF's body. The 413
 * has two messages and no `code`, so which one is told from the file that was sent:
 * one within 5 MB was refused for its pixels.
 */
function uploadFailure(error, file) {
  if (!(error instanceof ApiError)) {
    return { variant: 'error', title: PROFILE_TEXT.pictureUploadFailed, text: messageForStatus() }
  }
  if (error.status === 429 && error.code === PICTURE_BUSY_CODE) {
    // Not the uploader's doing, and nothing was stored: said as information.
    return { variant: 'info', title: PROFILE_TEXT.pictureBusyTitle, text: PROFILE_TEXT.pictureBusy(whenToRetry(error.retryAfter)) }
  }
  let text
  switch (error.status) {
    case 400:
      text = PROFILE_TEXT.pictureNotSubmitted
      break
    case 413:
      text = file.size > MAX_PICTURE_BYTES ? PROFILE_TEXT.pictureTooLarge : PROFILE_TEXT.pictureTooManyPixels
      break
    case 415:
      text = PROFILE_TEXT.pictureUnsupported
      break
    case 429:
      text = PROFILE_TEXT.pictureRateLimited(whenToRetry(error.retryAfter))
      break
    default:
      text = error.message
  }
  return { variant: 'error', title: PROFILE_TEXT.pictureUploadFailed, text }
}

/**
 * The signed-in user's own account (#119), on the routes D-137 built for it.
 *
 * **The password change** posts `current_password` and `new_password` to
 * `POST /api/auth/change-password`, under FR-01's rules: registration's checks and
 * its requirements panel, and Change password disabled until every check passes. A
 * 400 puts each field's messages under that field, a wrong current password
 * included, which the server never answers with a 401. The session that made the
 * change stays signed in; every other one ends.
 *
 * **The picture** goes to `POST /api/users/me/picture` as one multipart part,
 * `picture`, and Remove takes it away with `DELETE /api/users/me/picture`, once the
 * app's confirmation dialogue has been confirmed (Benjamin's answer 4, 18 November
 * 2026). Remove with a chosen picture not yet sent takes the choice away without
 * asking, since nothing on the server is deleted. After an upload or a removal, the
 * session's user is read again (`useAuth().refresh()`), so the header
 * and every list show the change. A file over 5 MB, or not a PNG, JPEG or WebP, is
 * refused before it is sent. The one file input is hidden and out of the tab order:
 * "Change picture" and "Choose a picture" are buttons that open it, which the
 * keyboard reaches and the focus ring shows.
 *
 * **One request at a time** (the contract's CHG-3). A password change gives this
 * session a new key and deletes the old one, so a request sent with the old key and
 * answered after the change gets a 401 that clears the new key's cookie: the user
 * would be signed out by their own change. So while any of this page's requests is
 * in flight, the page sends nothing else, and its buttons say so by being disabled.
 *
 * **A logout waits for the change too** (LOG-1). The header's Log out is not this
 * page's, so the change is handed to the auth provider (`trackAccountChange`), and a
 * logout pressed while it is in flight is sent once it has answered, with the cookie
 * that answer left: the new key's after a 200. Sent at once, it would end the old key,
 * and the change's 200 would leave the browser signed in under the new one after
 * "You've been logged out".
 */
export default function Profile() {
  useDocumentTitle(PROFILE_TEXT.heading)
  const { user, loading, refresh, trackAccountChange } = useAuth()
  const requirementsId = useId()

  /* ---- Password state ---- */
  const [values, setValues] = useState(EMPTY_PASSWORDS)
  const [touched, setTouched] = useState({})
  const [serverErrors, setServerErrors] = useState({})
  const [passwordFormError, setPasswordFormError] = useState(null)
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  /* ---- Picture state ---- */
  const [pictureFile, setPictureFile] = useState(null)
  const [picturePreview, setPicturePreview] = useState(null)
  // {variant, title, text}: a refusal before sending, the server's answer, or a success.
  const [pictureNotice, setPictureNotice] = useState(null)
  // 'upload' or 'remove' while that request is in flight.
  const [pictureWork, setPictureWork] = useState(null)
  // {seconds}: a `picture_busy` 429's Retry-After, while it runs.
  const [busyHold, setBusyHold] = useState(null)
  // Answer 4: the dialogue that asks before the saved picture is removed is open.
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const fileInputRef = useRef(null)
  // Where focus goes when the dialogue closes and Remove cannot take it back, as after a
  // removal, which leaves nothing to remove: the section's own heading.
  const pictureHeadingRef = useRef(null)

  // The request in flight, set before the state that disables the buttons renders,
  // so a second press or an Enter that lands first is refused here.
  const inFlight = useRef(null)

  // `picture_busy`: Upload is held back until the server's Retry-After has passed.
  useEffect(() => {
    if (!busyHold) return undefined
    const timer = setTimeout(() => setBusyHold(null), busyHold.seconds * 1000)
    return () => clearTimeout(timer)
  }, [busyHold])

  // The preview's object URL is let go once it is replaced or the page is left.
  useEffect(() => {
    if (!picturePreview) return undefined
    return () => {
      if (typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(picturePreview)
    }
  }, [picturePreview])

  /* ---- Loading / not signed in ---- */
  if (loading) {
    return (
      <div className="profile-page">
        <h1>{PROFILE_TEXT.heading}</h1>
        <p>Loading your profile…</p>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  /* ---- Change password ---- */
  const clientErrors = validatePasswordChange(values)
  const canSubmit = Object.keys(clientErrors).length === 0
  const working = savingPassword || pictureWork !== null

  // What shows under each field, as registration decides it: a client message once
  // the field has been left, except the new password's, whose feedback is the
  // requirements panel beside it; and the server's messages until the field changes.
  const fieldErrors = { ...serverErrors }
  for (const [field, message] of Object.entries(clientErrors)) {
    if (field !== 'newPassword' && touched[field]) fieldErrors[field] = message
  }

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    // A server message is about the value that was sent; editing it clears it.
    setServerErrors((current) => {
      if (!(name in current)) return current
      const next = { ...current }
      delete next[name]
      return next
    })
  }

  function handleBlur(event) {
    const { name } = event.target
    setTouched((current) => (current[name] ? current : { ...current, [name]: true }))
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault()
    // CHG-3: nothing else is sent until the request in flight has answered.
    if (inFlight.current) return
    setPasswordFormError(null)
    setPasswordSuccess(false)
    if (!canSubmit) {
      // Unreachable from the button, which is disabled, but Enter submits too.
      setTouched({ currentPassword: true, newPassword: true, confirmPassword: true })
      return
    }

    inFlight.current = 'password'
    setSavingPassword(true)
    try {
      // LOG-1: handed to the auth provider, so a logout waits for its answer.
      await trackAccountChange(
        changePassword({ currentPassword: values.currentPassword, newPassword: values.newPassword }),
      )
      setValues(EMPTY_PASSWORDS)
      setTouched({})
      setServerErrors({})
      setPasswordSuccess(true)
    } catch (error) {
      const fields = passwordFieldErrors(error)
      setServerErrors(fields)
      setPasswordFormError(Object.keys(fields).length > 0 ? null : passwordFailure(error))
    } finally {
      inFlight.current = null
      setSavingPassword(false)
    }
  }

  /* ---- Profile picture ---- */
  function openPicker() {
    fileInputRef.current?.click()
  }

  function handlePictureChosen(event) {
    const input = event.target
    const file = input.files?.[0] ?? null
    // Cleared, so choosing the same file again, after a refusal say, is a change too.
    input.value = ''
    if (!file) return
    setPictureNotice(null)
    const refusal = pictureRefusal(file)
    if (refusal) {
      setPictureFile(null)
      setPicturePreview(null)
      setPictureNotice({ variant: 'error', title: PROFILE_TEXT.pictureUploadFailed, text: refusal })
      return
    }
    setPictureFile(file)
    setPicturePreview(typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : null)
  }

  async function handlePictureSubmit(event) {
    event.preventDefault()
    if (!pictureFile || busyHold || inFlight.current) return
    const sent = pictureFile
    inFlight.current = 'upload'
    setPictureWork('upload')
    setPictureNotice(null)
    try {
      await uploadProfilePicture(sent)
      setPictureFile(null)
      setPicturePreview(null)
      setPictureNotice({ variant: 'info', title: PROFILE_TEXT.pictureUpdatedTitle, text: PROFILE_TEXT.pictureUpdated })
      // Read again before anything else is sent, so the header shows the new picture.
      await refresh()
    } catch (error) {
      setPictureNotice(uploadFailure(error, sent))
      if (error instanceof ApiError && error.status === 429 && error.code === PICTURE_BUSY_CODE && error.retryAfter > 0) {
        setBusyHold({ seconds: error.retryAfter })
      }
    } finally {
      inFlight.current = null
      setPictureWork(null)
    }
  }

  function handleRemove() {
    if (pictureFile) {
      // #119's Remove: the chosen picture goes, and nothing is sent, so nothing asks.
      setPictureFile(null)
      setPicturePreview(null)
      setPictureNotice(null)
      return
    }
    if (!user.picture || inFlight.current) return
    // Answer 4: the saved picture is deleted only once the dialogue is confirmed.
    setConfirmingRemove(true)
  }

  function cancelRemove() {
    // Not while the removal is in flight: the dialogue says "Removing…" until it answers.
    if (pictureWork !== 'remove') setConfirmingRemove(false)
  }

  // The dialogue stays open, busy, until the DELETE has answered, as the app's other
  // deletions do; it closes in `finally`. Focus then goes back to Remove, or to the
  // section's heading when Remove is disabled because nothing is left to remove.
  async function confirmRemove() {
    if (!user.picture || inFlight.current) return
    inFlight.current = 'remove'
    setPictureWork('remove')
    setPictureNotice(null)
    try {
      await removeProfilePicture()
      setPictureNotice({ variant: 'info', title: PROFILE_TEXT.pictureRemovedTitle, text: PROFILE_TEXT.pictureRemoved })
      await refresh()
    } catch (error) {
      setPictureNotice({
        variant: 'error',
        title: PROFILE_TEXT.pictureRemoveFailed,
        text: error instanceof ApiError ? error.message : messageForStatus(),
      })
    } finally {
      inFlight.current = null
      setPictureWork(null)
      setConfirmingRemove(false)
    }
  }

  /* ---- Render ---- */
  const administrator = user.role === ROLES.administrator
  const roleLabel = administrator ? ROLES.administrator : ROLES.employee
  // Remove's name says which picture it takes away. While the saved one is being removed,
  // the dialogue says "Removing…", and Remove waits behind it, disabled.
  const removeLabel = pictureFile ? PROFILE_TEXT.removeChosenLabel : PROFILE_TEXT.removeSavedLabel

  return (
    <div className="profile-page">
      <div className="profile-header">
        <h1>{PROFILE_TEXT.heading}</h1>
        <p className="profile-intro">
          Manage your account details, password and profile picture.
        </p>
      </div>

      {/* ---- Profile info card ---- */}
      <section className="profile-card">
        <div className="profile-avatar">
          {/* Decorative: the name is beside it, in the heading below. */}
          {picturePreview ? (
            <img src={picturePreview} alt="" className="profile-avatar__image" />
          ) : (
            <Avatar
              name={user.name}
              picture={user.picture}
              size={null}
              imageClassName="profile-avatar__image"
              initialsClassName="profile-avatar__placeholder"
            />
          )}
          <button
            type="button"
            className="profile-avatar__upload"
            disabled={pictureWork !== null}
            onClick={openPicker}
          >
            {PROFILE_TEXT.changePicture}
          </button>
        </div>
        <div className="profile-details">
          <h2>{user.name}</h2>
          <p className="profile-email">{user.email}</p>
          <span className={`profile-role ${administrator ? 'profile-role--administrator' : 'profile-role--employee'}`}>
            {roleLabel}
          </span>
          <p className="profile-member">
            Member since{' '}
            {new Date(user.created_at).toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'long',
            })}
          </p>
        </div>
      </section>

      {/* ---- Change password ---- */}
      <section className="profile-section">
        <h2>{PROFILE_TEXT.passwordHeading}</h2>
        {passwordFormError ? (
          <Notice variant="error" title={PROFILE_TEXT.passwordChangeFailed}>
            {passwordFormError}
          </Notice>
        ) : null}
        {passwordSuccess ? (
          <Notice variant="info" title={PROFILE_TEXT.passwordChangedTitle}>
            {`${PROFILE_TEXT.passwordChanged} ${PROFILE_TEXT.passwordChangedSessions}`}
          </Notice>
        ) : null}
        <form className="profile-form" onSubmit={handlePasswordSubmit} noValidate>
          <div className="profile-form__row">
            <TextInput
              label={PROFILE_TEXT.currentPasswordLabel}
              name="currentPassword"
              type="password"
              autoComplete="current-password"
              required
              value={values.currentPassword}
              error={fieldErrors.currentPassword}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            {/* The requirements panel describes the field, as on registration. */}
            <TextInput
              label={PROFILE_TEXT.newPasswordLabel}
              name="newPassword"
              type="password"
              autoComplete="new-password"
              required
              value={values.newPassword}
              error={fieldErrors.newPassword}
              describedBy={requirementsId}
              onChange={handleChange}
              onBlur={handleBlur}
            />
          </div>
          <PasswordRequirements id={requirementsId} password={values.newPassword} />
          <TextInput
            label={PROFILE_TEXT.confirmPasswordLabel}
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            required
            value={values.confirmPassword}
            error={fieldErrors.confirmPassword}
            onChange={handleChange}
            onBlur={handleBlur}
          />
          <div className="profile-form__actions">
            <Button type="submit" loading={savingPassword} disabled={!canSubmit || working}>
              {savingPassword ? PROFILE_TEXT.changingPassword : PROFILE_TEXT.changePassword}
            </Button>
            {/* A disabled button cannot be focused, so the reason sits beside it. */}
            {!canSubmit && !savingPassword ? <p className="profile-form__gate">{PROFILE_TEXT.passwordGate}</p> : null}
          </div>
        </form>
      </section>

      {/* ---- Profile picture upload ---- */}
      <section className="profile-section">
        {/* Focusable from script only: where focus goes after a removal (answer 4). */}
        <h2 ref={pictureHeadingRef} tabIndex={-1}>
          Profile picture
        </h2>
        {pictureNotice ? (
          <Notice variant={pictureNotice.variant} title={pictureNotice.title}>
            {pictureNotice.text}
          </Notice>
        ) : null}
        <form className="profile-form" onSubmit={handlePictureSubmit} noValidate>
          {/* The one file input, hidden and out of the tab order. The two buttons
              that open it are what the keyboard reaches. */}
          <input
            ref={fileInputRef}
            type="file"
            accept={PICTURE_TYPES.join(',')}
            hidden
            tabIndex={-1}
            onChange={handlePictureChosen}
          />
          <div className="profile-form__row">
            <Button
              variant="secondary"
              disabled={pictureWork !== null}
              aria-label={pictureFile ? PROFILE_TEXT.choosePictureChosen(pictureFile.name) : undefined}
              onClick={openPicker}
            >
              {pictureFile ? pictureFile.name : PROFILE_TEXT.choosePicture}
            </Button>
            <Button
              disabled={working || (!pictureFile && !user.picture)}
              aria-label={removeLabel}
              onClick={handleRemove}
            >
              {PROFILE_TEXT.removePicture}
            </Button>
          </div>
          {picturePreview && (
            <div className="profile-picture__preview">
              <img src={picturePreview} alt={PROFILE_TEXT.previewAlt} />
            </div>
          )}
          <div className="profile-form__actions">
            <Button
              type="submit"
              loading={pictureWork === 'upload'}
              disabled={working || !pictureFile || busyHold !== null}
            >
              {pictureWork === 'upload' ? PROFILE_TEXT.uploadingPicture : PROFILE_TEXT.uploadPicture}
            </Button>
          </div>
        </form>
      </section>

      {/* Answer 4: the app's confirmation dialogue, as a document's, a meeting's and a
          tag's deletion use it. It takes focus when it opens and gives it back when it
          closes (components/Dialog.jsx). */}
      {confirmingRemove ? (
        <Dialog
          title={PROFILE_TEXT.removeConfirmTitle}
          confirmLabel={PROFILE_TEXT.removeConfirmLabel}
          busyLabel={PROFILE_TEXT.removingPicture}
          cancelLabel={PROFILE_TEXT.removeCancel}
          busy={pictureWork === 'remove'}
          returnFocusRef={pictureHeadingRef}
          onConfirm={confirmRemove}
          onCancel={cancelRemove}
        >
          <p>{PROFILE_TEXT.removeConfirmBody}</p>
        </Dialog>
      ) : null}
    </div>
  )
}
