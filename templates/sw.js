/* MTG Vault service worker — served at root scope (/sw.js) so it controls the
   whole app. Minimal app-shell cache: cache-first for static assets, otherwise
   network with a cached fallback. Enough to make the app installable and resilient
   to brief connectivity blips. */
const CACHE = "mtg-vault-v1";
const SHELL = [
  "/",
  "/static/favicon.svg",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // never cache POSTs (CSRF-protected actions)
  // Cache-first for our static assets; network-first for everything else.
  if (req.url.includes("/static/")) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  } else {
    event.respondWith(fetch(req).catch(() => caches.match(req)));
  }
});
