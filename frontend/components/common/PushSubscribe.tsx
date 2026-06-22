"use client"

import { useState, useEffect, useCallback } from "react"

function urlB64ToUint8Array(base64: string) {
  // Convert VAPID public key from base64 to Uint8Array
  const padding = "=".repeat((4 - (base64.length % 4)) % 4)
  const raw = atob(base64.replace(/-/g, "+").replace(/_/g, "/") + padding)
  const arr = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) {
    arr[i] = raw.charCodeAt(i)
  }
  return arr
}

const VAPID_PUBLIC = "BBzdEi25XbpOmxeBGzmXzMOMa0eJhVer0vaAj969YNUbo6G3xduShiI3YWRJGdWciYf0FiKehgMOIBtdJIK0UM4"
const STORAGE_KEY = "wc26_push_subscribed"
const DISMISS_KEY = "wc26_push_dismissed_at"
// Mirrors the tour version in FirstVisitTour.tsx — bumping that re-shows the
// tour, so we use it as the "user has seen the welcome" signal.
const TOUR_KEY = "wc26_tour_seen"
const TOUR_VERSION = "1"
// Engagement gate — set by /match/[id] and /value pages when the user actually
// reads one. Until that fires, the notify prompt stays silent: no point
// asking a fresh visitor for notifications before they've seen what we do.
const ENGAGED_KEY = "wc26_engaged"
// Re-ask cooldown after a "Not now" dismissal. 7 days is the standard floor
// most modern apps use before re-asking for push permission.
const REDISPLAY_AFTER_MS = 7 * 24 * 60 * 60 * 1000

export function PushSubscribe() {
  const [subscribed, setSubscribed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [supported, setSupported] = useState(false)
  const [showPrompt, setShowPrompt] = useState(false)

  useEffect(() => {
    setSupported("Notification" in window && "serviceWorker" in navigator)
    if (typeof window === "undefined") return
    if (localStorage.getItem(STORAGE_KEY) === "true") {
      setSubscribed(true)
      return
    }
    // Gate 1: don't ambush before the welcome tour has been seen + dismissed.
    if (localStorage.getItem(TOUR_KEY) !== TOUR_VERSION) return
    // Gate 2: only after the user has engaged with a real content page once.
    if (localStorage.getItem(ENGAGED_KEY) !== "1") return
    // Gate 3: honour a recent dismissal (7-day cooldown).
    const dismissedAt = Number(localStorage.getItem(DISMISS_KEY) || 0)
    if (dismissedAt && Date.now() - dismissedAt < REDISPLAY_AFTER_MS) return
    // Long-tail delay so the prompt doesn't compete with the page paint.
    const t = setTimeout(() => setShowPrompt(true), 4000)
    return () => clearTimeout(t)
  }, [])

  const subscribe = useCallback(async () => {
    setLoading(true)
    try {
      const perm = await Notification.requestPermission()
      if (perm !== "granted") return

      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlB64ToUint8Array(VAPID_PUBLIC),
      })

      // Store subscription on backend
      await fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sub.toJSON()),
      })
      localStorage.setItem(STORAGE_KEY, "true")
      setSubscribed(true)
      setShowPrompt(false)
    } catch {
      // silently fail — not critical
    } finally {
      setLoading(false)
    }
  }, [])

  if (!supported || subscribed || !showPrompt) return null

  return (
    <div className="fixed bottom-20 left-4 right-4 z-50 max-w-sm mx-auto rounded-xl border border-emerald-500/30 bg-surface-1/95 backdrop-blur shadow-lg p-3.5 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex items-start gap-3">
        <span className="text-lg shrink-0">🔔</span>
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-bold text-white">Get value pick alerts</p>
          <p className="text-[11px] text-slate-400 leading-snug mt-0.5">
            Browser notification when the model finds an edge before kickoff.
          </p>
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        <button
          onClick={subscribe}
          disabled={loading}
          className="flex-1 text-[11px] font-bold px-3 py-2 rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 disabled:opacity-50 transition-colors"
        >
          {loading ? "..." : "Notify me"}
        </button>
        <button
          onClick={() => {
            setShowPrompt(false)
            try {
              localStorage.setItem(DISMISS_KEY, String(Date.now()))
            } catch { /* private mode / storage disabled */ }
          }}
          className="text-[11px] px-3 py-2 rounded-lg text-slate-500 hover:text-slate-300"
        >
          Not now
        </button>
      </div>
    </div>
  )
}
