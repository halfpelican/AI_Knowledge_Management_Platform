import { useCallback, useState } from 'react'

/**
 * Which transcript passages are open, for src/components/PassageReferences.jsx.
 *
 * One set of panel ids for a whole list of referenced elements (the sentences of
 * a summary, say), held by whatever renders them, because a hook cannot be called
 * once per sentence. Each reference opens and closes its own panel and no other.
 *
 * @returns {[Set<string>, (panelId: string) => void]} the open panel ids, and the toggle
 */
export default function usePassagePanels() {
  const [open, setOpen] = useState(() => new Set())
  const toggle = useCallback((panelId) => {
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(panelId)) next.delete(panelId)
      else next.add(panelId)
      return next
    })
  }, [])
  return [open, toggle]
}
