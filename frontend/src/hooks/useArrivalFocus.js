import { useEffect } from 'react'

/**
 * Puts focus on a heading once the view a reader switched to has settled.
 *
 * The knowledge map has two views at one route (D-138), and the link that switches
 * between them is removed with the view it was followed from. Left alone, focus
 * would fall back to the top of the document, and a keyboard or screen-reader user
 * would have to find the page again.
 *
 * The page keeps a note of the view a switch led to (src/pages/KnowledgeMap.jsx),
 * and `takeArrival(view)` answers whether that note names `view`, clearing it when
 * it does. The view asks here, once it is no longer loading: on its map, its empty
 * state or its failure alike. A page opened at either view by its address has no
 * note, and its focus is left alone.
 *
 * The note names a view and is not a flag, because an effect of the view being left
 * can still be pending when the link is followed. A flag would be spent by that
 * effect, on a heading about to be removed (src/pages/DocumentRepository.jsx says
 * the same of its own pending focus).
 *
 * @param {(view: string) => boolean} takeArrival Whether a switch on this page led to `view`; asking spends it.
 * @param {string} view The view calling this.
 * @param {boolean} settled Whether the view has stopped loading.
 * @param {{current: HTMLElement|null}} targetRef The heading that takes focus.
 */
export default function useArrivalFocus(takeArrival, view, settled, targetRef) {
  useEffect(() => {
    if (settled && takeArrival(view)) targetRef.current?.focus()
  }, [takeArrival, view, settled, targetRef])
}
