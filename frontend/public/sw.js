// WC2026 Predictor Service Worker
// Caches critical assets for instant repeat loads, handles push notifications
// Bump on every release that adds new UI surface. v4 (2026-06-24): force
// installed PWAs to fetch the follow-notifs JS bundle. Without this bump,
// service-worker installs persist the OLD cache index forever and users
// never see new bells / new component code.
const CACHE = 'wc26-v4'
const PRECACHE = [
  '/',
  '/value',
  '/groups',
  '/bracket',
  '/performance',
  '/predictions',
  '/manifest.json',
]

// Install: pre-cache shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE).catch(() => {}))
  )
  self.skipWaiting()
})

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

// Fetch: network-first with cache fallback for navigations, cache-first for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  // API + data requests: network only
  if (url.pathname.startsWith('/_next/') || url.pathname.match(/\.(png|svg|ico|woff2?)$/)) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    )
    return
  }
  // Page navigations: network-first, fallback to cache
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone()
          caches.open(CACHE).then((cache) => cache.put(event.request, clone))
          return res
        })
        .catch(() => caches.match(event.request))
    )
  }
})

// Push notifications
self.addEventListener('push', (event) => {
  if (!event.data) return
  const data = event.data.json()
  const title = data.title || 'WC2026 Value Alert'
  const options = {
    body: data.body || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: data.match_id || 'wc26-value',
    data: { url: data.url || '/value' },
    requireInteraction: data.requireInteraction ?? false,
    vibrate: [200, 100, 200],
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/value'
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clients) => {
      const existing = clients.find((c) => c.url.includes(url))
      if (existing) {
        existing.focus()
      } else {
        self.clients.openWindow(url)
      }
    })
  )
})
