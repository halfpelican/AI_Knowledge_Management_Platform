import { APP_TITLE } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'

export default function Home() {
  useDocumentTitle('Alpha build')

  return (
    <>
      <h1>Alpha build under construction</h1>
      <p>
        The {APP_TITLE} alpha build is under construction. Feature screens will appear here as each requirement
        is completed for the M6 gate.
      </p>
    </>
  )
}
