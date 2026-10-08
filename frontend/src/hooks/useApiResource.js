import { useCallback, useEffect, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'

/**
 * Read one thing from the API, with the three states every read screen needs:
 * loading, loaded, and failed with a retry.
 *
 * The loader is called with `{ signal }` and is expected to be one of the
 * endpoint helpers in src/api — the components using this never call the client
 * themselves. It must be **stable**: either a module-level function, as
 * `listMeetings` is, or one wrapped in `useCallback` with whatever it closes
 * over in its dependencies, as a detail route's id is. The loader is the
 * effect's only dependency besides the retry counter, so a changed id re-reads
 * and an unchanged one does not, without a ref holding a value one render stale.
 *
 * An in-flight request is aborted when the component unmounts or the loader
 * changes, and an AbortError is not an error state: it is this screen cancelling
 * its own request.
 *
 * Every other failure is normalised to an `ApiError`, so a caller can branch on
 * `error.status` (a 403 renders the not-permitted notice; a 404 on a detail
 * route renders "not found") and can render `error.message` as-is — it is fixed,
 * user-facing text and never a backend string.
 *
 * @param {(options: {signal: AbortSignal}) => Promise<unknown>} loader
 */
export default function useApiResource(loader) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Bumped by reload(): a retry, or a list a write has made stale.
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller

    async function read() {
      let result = null
      let failure = null
      try {
        result = await loader({ signal })
      } catch (caught) {
        if (caught?.name === 'AbortError') return
        failure =
          caught instanceof ApiError
            ? caught
            : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
      }
      if (signal.aborted) return
      if (!failure) setData(result)
      setError(failure)
      setLoading(false)
    }

    read()
    return () => controller.abort()
  }, [loader, reloadKey])

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    setReloadKey((key) => key + 1)
  }, [])

  return { data, loading, error, reload, setData }
}
