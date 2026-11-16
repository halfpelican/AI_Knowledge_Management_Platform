import { post, upload } from './client.js'

export function changePassword({ currentPassword, newPassword }) {
  return post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export function uploadProfilePicture(file) {
  const formData = new FormData()
  formData.append('picture', file)
  return upload('/users/me/picture', formData)
}