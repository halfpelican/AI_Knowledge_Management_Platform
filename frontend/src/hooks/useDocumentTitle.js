import { useEffect } from 'react'
import { APP_TITLE } from '../constants.js'

/** Sets the browser tab title so every route announces where the user is (WCAG 2.4.2). */
export default function useDocumentTitle(pageTitle) {
  useEffect(() => {
    document.title = pageTitle ? `${pageTitle} - ${APP_TITLE}` : APP_TITLE
  }, [pageTitle])
}
