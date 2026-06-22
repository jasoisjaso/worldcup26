"use client"
import { useEffect } from "react"

const ENGAGED_KEY = "wc26_engaged"

/** Sets the wc26_engaged localStorage flag on mount. Read by PushSubscribe to
 *  gate the notify-me popup until the visitor has actually opened a content
 *  page (value board, single match). Avoids ambushing fresh landings with two
 *  popups before they've seen what the site does. */
export function EngagementMarker() {
  useEffect(() => {
    try {
      localStorage.setItem(ENGAGED_KEY, "1")
    } catch { /* private mode / storage disabled */ }
  }, [])
  return null
}
