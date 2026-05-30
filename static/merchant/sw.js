/* Auguspay(TM) POS service worker -- caches the app shell so it boots offline.
 *
 * (c) 2026 Kuldeep Chotiya. All Rights Reserved.
 * Proprietary software -- see /LICENSE in the project root.
 *
 * IMPORTANT: we do NOT cache the /merchant/ HTML page itself.  Its content
 * depends on session state (register vs dashboard), so a cached copy would
 * pin a logged-out user on the register page even after they sign in.
 * For navigations we use network-first with a tiny offline fallback.
 */
const CACHE = 'auguspay-pos-v16';
const SHELL = [
  '/static/merchant/style.css',
  '/static/merchant/app.js',
  '/static/merchant/install.js',
  '/static/merchant/manifest.webmanifest',
  '/static/merchant/icon.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // never touch API calls or SSE - must always hit the network
  if (url.pathname.startsWith('/merchant/api/')) return;

  // navigations (HTML) -> network-first, no cache write.
  // This is critical: /merchant/ renders either the register page OR the
  // dashboard depending on session, so caching it would break login.
  if (e.request.mode === 'navigate' ||
      (e.request.headers.get('accept') || '').includes('text/html')) {
    e.respondWith(
      fetch(e.request).catch(() =>
        new Response(
          '<h1>Offline</h1><p>Open this page once online to install Auguspay.</p>',
          { headers: { 'Content-Type': 'text/html' } }
        )
      )
    );
    return;
  }

  // static assets -> stale-while-revalidate
  e.respondWith(
    caches.match(e.request).then((cached) => {
      const network = fetch(e.request).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
