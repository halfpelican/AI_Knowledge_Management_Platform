import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '../api/client.js'
import { changePassword, uploadProfilePicture } from '../api/profile.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import PasswordInput from '../components/PasswordInput.jsx'
import TextInput from '../components/TextInput.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import './Profile.css'

  /* ---- State ---- */
  const [passwordErrors, setPasswordErrors] = useState({})
  const [passwordFormError, setPasswordFormError] = useState(null)
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  const [uploadError, setUploadError] = useState(null)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const [uploadingPicture, setUploadingPicture] = useState(false)
  const [pictureFile, setPictureFile] = useState(null)
  const [picturePreview, setPicturePreview] = useState(null)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

export default function Profile() {
  useDocumentTitle('My Profile')
  const { user, loading } = useAuth()

  /* ---- Loading / not signed in ---- */
  if (loading) {
    return (
      <div className="profile-page">
        <h1>My Profile</h1>
        <p>Loading your profile…</p>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  /* ---- Change password ---- */
  function validatePasswordForm() {
    const errors = {}
    if (!currentPassword) errors.currentPassword = 'Enter your current password.'
    if (!newPassword) errors.newPassword = 'Enter a new password.'
    else if (newPassword.length < 8) errors.newPassword = 'Password must be at least 8 characters.'
    if (!confirmPassword) errors.confirmPassword = 'Re-enter your new password.'
    else if (confirmPassword !== newPassword) errors.confirmPassword = 'The two passwords do not match.'
    return errors
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault()
    const errors = validatePasswordForm()
    setPasswordErrors(errors)
    setPasswordFormError(null)
    setPasswordSuccess(false)
    if (Object.keys(errors).length > 0) return

    setSavingPassword(true)
    try {
      await changePassword({ currentPassword, newPassword })
      setPasswordSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.status === 400 && caught.details) {
          const extracted = extractFieldErrors(caught, [
            'currentPassword',
            'newPassword',
            'confirmPassword',
          ])
          setPasswordErrors(extracted.fieldErrors)
          setPasswordFormError(extracted.formError)
        } else if (caught.status === 401) {
          setPasswordFormError('Your current password is incorrect.')
        } else {
          setPasswordFormError(caught.message)
        }
      } else {
        setPasswordFormError('Could not change your password. Please try again.')
      }
    } finally {
      setSavingPassword(false)
    }
  }

  /* ---- Profile picture ---- */
  function handlePictureChange(event) {
    const file = event.target.files?.[0] ?? null
    setPictureFile(file)
    setUploadError(null)
    setUploadSuccess(false)
    if (file) {
      setPicturePreview(URL.createObjectURL(file))
    } else {
      setPicturePreview(null)
    }
  }

  async function handlePictureSubmit(event) {
    event.preventDefault()
    if (!pictureFile) return
    setUploading(true)
    setUploadError(null)
    setUploadSuccess(false)
    try {
      await uploadProfilePicture(pictureFile)
      setUploadSuccess(true)
      setPictureFile(null)
      setPicturePreview(null)
      event.target.reset()
    } catch (caught) {
      if (caught instanceof ApiError) {
        setUploadError(caught.message)
      } else {
        setUploadError('Could not upload your picture. Please try again.')
      }
    } finally {
      setUploading(false)
    }
  }

  /* ---- Render ---- */
  const roleLabel = user.role === 'Administrator' ? 'Administrator' : 'Employee'
  const initial = user.name ? user.name[0].toUpperCase() : 'U'

  return (
    <div className="profile-page">
      <div className="profile-header">
        <h1>My Profile</h1>
        <p className="profile-intro">
          Manage your account details, password and profile picture.
        </p>
      </div>

      {/* ---- Profile info card ---- */}
      <section className="profile-card">
        <div className="profile-avatar">
          {picturePreview ? (
            <img src={picturePreview} alt="Profile picture" className="profile-avatar__image" />
          ) : (
            <div className="profile-avatar__placeholder">{initial}</div>
          )}
          <label className="profile-avatar__upload">
            <input type="file" accept="image/*" onChange={handlePictureChange} />
            Change picture
          </label>
        </div>
        <div className="profile-details">
          <h2>{user.name}</h2>
          <p className="profile-email">{user.email}</p>
          <span
            className={`profile-role ${user.role.toLowerCase()}`}
            style={{
              backgroundColor:
                user.role === 'Administrator' ? '#dcfce7' : '#dbeafe',
              color: user.role === 'Administrator' ? '#166534' : '#1e40af',
              borderColor:
                user.role === 'Administrator' ? '#bbf7d0' : '#bfdbfe',
            }}
          >
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
        <h2>Change password</h2>
        {passwordFormError ? (
          <Notice variant="error" title="Could not change password">
            {passwordFormError}
          </Notice>
        ) : null}
        {passwordSuccess ? (
          <Notice variant="info" title="Password changed">
            Your password has been changed successfully.
          </Notice>
        ) : null}
        <form className="profile-form" onSubmit={handlePasswordSubmit} noValidate>
          <div className="profile-form__row">
            <TextInput
              label="Current password"
              name="currentPassword"
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              error={passwordErrors.currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
            <TextInput
              label="New password"
              name="newPassword"
              type="password"
              autoComplete="new-password"
              required
              value={newPassword}
              error={passwordErrors.newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              hint="At least 8 characters."
            />
          </div>
          <TextInput
            label="Confirm new password"
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            required
            value={confirmPassword}
            error={passwordErrors.confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
          <div className="profile-form__actions">
            <Button type="submit" loading={savingPassword} disabled={savingPassword}>
              {savingPassword ? 'Saving…' : 'Change password'}
            </Button>
          </div>
        </form>
      </section>

      {/* ---- Profile picture upload ---- */}
      <section className="profile-section">
        <h2>Profile picture</h2>
        {uploadError ? (
          <Notice variant="error" title="Could not upload picture">
            {uploadError}
          </Notice>
        ) : null}
        {uploadSuccess ? (
          <Notice variant="info" title="Picture updated">
            Your profile picture has been updated.
          </Notice>
        ) : null}
        <form className="profile-form" onSubmit={handlePictureSubmit} noValidate>
          <div className="profile-form__row">
            <label className="profile-picture__label">
              <input type="file" accept="image/*" onChange={handlePictureChange} hidden />
              {pictureFile ? pictureFile.name : 'Choose a picture'}
            </label>
            <Button
              type="button"
              onClick={() => {
                setPictureFile(null)
                setPicturePreview(null)
                setUploadError(null)
                setUploadSuccess(false)
              }}
            >
              Remove
            </Button>
          </div>
          {picturePreview && (
            <div className="profile-picture__preview">
              <img src={picturePreview} alt="Preview" />
            </div>
          )}
          <div className="profile-form__actions">
            <Button
              type="submit"
              loading={uploadingPicture}
              disabled={uploadingPicture || !pictureFile}
            >
              {uploadingPicture ? 'Uploading…' : 'Upload picture'}
            </Button>
          </div>
        </form>
      </section>
    </div>
  )
}
