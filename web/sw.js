/* 그땐 얼마? service worker — release tag: 20261010f (keep in step with the
 * ?v= tags in index.html; bump both together on every release). */
const CACHE = "geuttaen-20261010f";
const SHELL = [
  "./",
  "index.html",
  "style.css?v=20261010f",
  "config.js?v=20261010f",
  "app.js?v=20261010f",
  "manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Data files: serve the cached copy instantly, refresh it in the
  // background so the next open is current (data updates weekly).
  if (url.origin === location.origin && url.pathname.includes("/data/")) {
    e.respondWith(
      caches.open(CACHE).then(async (c) => {
        const hit = await c.match(req, { ignoreSearch: true });
        const net = fetch(req)
          .then((r) => {
            if (r.ok) c.put(req, r.clone());
            return r;
          })
          .catch(() => hit);
        return hit || net;
      })
    );
    return;
  }

  // Page navigations: fresh HTML first so releases show up, cache offline.
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const copy = r.clone();
          caches.open(CACHE).then((c) => c.put("index.html", copy));
          return r;
        })
        .catch(() => caches.match("index.html"))
    );
    return;
  }

  // App shell and fonts: cache-first.
  if (url.origin === location.origin || url.hostname === "fonts.gstatic.com") {
    e.respondWith(
      caches.match(req, { ignoreSearch: false }).then(
        (hit) =>
          hit ||
          fetch(req).then((r) => {
            if (r.ok || r.type === "opaque") {
              const copy = r.clone();
              caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return r;
          })
      )
    );
  }
  // Everything else (Kakao SDK, map tiles, Chart.js CDN) passes through.
});
