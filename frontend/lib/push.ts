// Shared push-subscription helper. Single source of truth for VAPID key,
// subscribe flow, endpoint storage. Used by the global PushSubscribe
// prompt (value picks) AND the per-match FollowBell on match cards.
//
// Subscriptions are anonymous, per-device. Endpoint string is stable —
// we cache it in localStorage so follow/unfollow calls have a key to
// pass to /api/push/follow-match without re-running the subscribe flow.

const VAPID_PUBLIC = "BBzdEi25XbpOmxeBGzmXzMOMa0eJhVer0vaAj969YNUbo6G3xduShiI3YWRJGdWciYf0FiKehgMOIBtdJIK0UM4"
const STORAGE_KEY = "wc26_push_subscribed"
const ENDPOINT_KEY = "wc26_push_endpoint"

function urlB64ToUint8Array(base64: string) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4)
  const raw = atob(base64.replace(/-/g, "+").replace(/_/g, "/") + padding)
  const arr = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i)
  return arr
}

export function pushSupported(): boolean {
  if (typeof window === "undefined") return false
  return "Notification" in window && "serviceWorker" in navigator && "PushManager" in window
}

export function getCachedEndpoint(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(ENDPOINT_KEY)
}

// iOS PWA gate: web push only works on iOS 16.4+ AND only when the PWA
// has been installed to the Home Screen. A Safari tab visit gives nothing.
// Detect: iOS device AND NOT in standalone display mode.
export function iosInstallRequired(): boolean {
  if (typeof window === "undefined") return false
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  if (!isIOS) return false
  const standalone =
    (window.navigator as { standalone?: boolean }).standalone === true ||
    window.matchMedia?.("(display-mode: standalone)").matches
  return !standalone
}

// EU iOS users on iOS 17.4+ get no push at all (DMA removed standalone
// PWA support). Detection is best-effort — language + timezone heuristic.
// False negative is fine; we'll just fail the subscribe gracefully.
export function isLikelyEUiOS(): boolean {
  if (typeof window === "undefined") return false
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  if (!isIOS) return false
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""
  return tz.startsWith("Europe/")
}

/** Ensure a Web Push subscription exists. Returns the endpoint string
 *  or null if the user denied / the browser doesn't support it.
 *  Idempotent — repeat calls return the cached endpoint when one exists. */
export async function ensureSubscribed(): Promise<string | null> {
  if (!pushSupported()) return null
  const cached = getCachedEndpoint()
  if (cached) {
    // Verify the browser still has it — Safari can drop subscriptions
    // when cache is purged.
    try {
      const reg = await navigator.serviceWorker.ready
      const existing = await reg.pushManager.getSubscription()
      if (existing && existing.endpoint === cached) return cached
    } catch {
      // fall through to fresh subscribe
    }
  }
  const perm = await Notification.requestPermission()
  if (perm !== "granted") return null
  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlB64ToUint8Array(VAPID_PUBLIC),
  })
  const subJson = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } }
  await fetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subJson),
  })
  localStorage.setItem(STORAGE_KEY, "true")
  localStorage.setItem(ENDPOINT_KEY, subJson.endpoint)
  return subJson.endpoint
}
