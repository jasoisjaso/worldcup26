"use client"
/**
 * Persistent bell icon that lets subscribed users toggle notification prefs and
 * unsubscribed users subscribe. Always visible in the TopBar when the browser supports
 * push — even if the user dismissed the one-shot toast.
 */
import { useState, useEffect, useCallback } from "react"

function urlB64ToUint8Array(base64: string) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4)
  const raw = atob(base64.replace(/-/g, "+").replace(/_/g, "/") + padding)
  const arr = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i)
  return arr
}

const VAPID = "BBzdEi25XbpOmxeBGzmXzMOMa0eJhVer0vaAj969YNUbo6G3xduShiI3YWRJGdWciYf0FiKehgMOIBtdJIK0UM4"
const STORAGE_KEY = "wc26_push_subscribed"

export function NotificationBell() {
  const [mounted, setMounted] = useState(false)
  const [subscribed, setSubscribed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

  useEffect(() => {
    setMounted(true)
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === "true") {
      setSubscribed(true)
      return
    }
    // Also check if we already have a push subscription via the browser
    navigator.serviceWorker?.ready.then(async (reg) => {
      const sub = await reg.pushManager.getSubscription()
      if (sub) {
        localStorage.setItem(STORAGE_KEY, "true")
        setSubscribed(true)
      }
    }).catch(() => {})
  }, [])

  const subscribe = useCallback(async () => {
    if (loading) return
    setLoading(true)
    try {
      // If the user already denied, we can't re-prompt. Show they need to go to settings.
      if (Notification.permission === "denied") {
        setShowTooltip(true)
        setTimeout(() => setShowTooltip(false), 5000)
        return
      }
      const perm = await Notification.requestPermission()
      if (perm !== "granted") {
        if (perm === "denied") {
          setShowTooltip(true)
          setTimeout(() => setShowTooltip(false), 5000)
        }
        return
      }
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlB64ToUint8Array(VAPID),
      })
      await fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sub.toJSON()),
      })
      localStorage.setItem(STORAGE_KEY, "true")
      setSubscribed(true)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [loading])

  const unsubscribe = useCallback(async () => {
    if (loading) return
    setLoading(true)
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) {
        await sub.unsubscribe()
      }
      localStorage.removeItem(STORAGE_KEY)
      setSubscribed(false)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [loading])

  // SSR + hydration: render nothing until mounted, so server HTML and client first
  // paint match. Then the post-mount render decides whether to show the bell.
  if (!mounted) return null
  if (!("Notification" in window) || !("serviceWorker" in navigator)) return null

  return (
    <div className="relative shrink-0">
      <button
        onClick={subscribed ? unsubscribe : subscribe}
        disabled={loading}
        className={`p-1.5 rounded-lg transition-all relative ${
          subscribed
            ? "text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
            : "text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 ring-1 ring-amber-500/30 animate-pulse"
        }`}
        aria-label={subscribed ? "Notifications on. Tap to turn off." : "Turn on notifications"}
      >
        {loading ? (
          <span className="w-5 h-5 flex items-center justify-center text-[14px] animate-pulse">⏳</span>
        ) : (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 10v-3a6 6 0 00-12 0v3l-1.5 2h15l-1.5-2z" />
            <path d="M11.73 16a2 2 0 01-3.46 0" />
            {!subscribed && <line x1="18" y1="1" x2="1" y2="19" stroke="#ef4444" strokeWidth="2" />}
          </svg>
        )}
      </button>

      {/* Tooltip when denied — shows how to re-enable */}
      {showTooltip && (
        <div className="fixed top-14 right-3 z-50 max-w-[260px] rounded-xl border border-amber-500/30 bg-surface-1/95 backdrop-blur shadow-lg p-3 animate-in fade-in slide-in-from-top-2">
          <p className="text-[11px] text-slate-300 leading-snug">
            Notifications were blocked. Tap the lock/info icon in your browser&lsquo;s address bar &rarr; Permissions &rarr; Allow.
          </p>
        </div>
      )}
    </div>
  )
}
