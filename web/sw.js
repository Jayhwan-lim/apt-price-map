/* 그땐 얼마? service worker — release tag: 20261028c (keep in step with the
 * ?v= tags in index.html; bump both together on every release). */
const CACHE = "geuttaen-20261028c";
const EXT_CACHE = "geuttaen-ext-v1"; // Kakao tiles + SDK: the heavy half of a cold open
const SHELL = [
  "./",
  "index.html",
  "style.css?v=20261028c",
  "config.js?v=20261028c",
  "app.js?v=20261028c",
  "map-metrics.js?v=20261028c",
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
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE && k !== EXT_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function trimExt(cache) {
  const keys = await cache.keys();
  if (keys.length > 400) await cache.delete(keys[0]);
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Kakao map tiles and the SDK script: cache-first so repeat opens paint
  // the map from disk instead of waiting on the tile CDN every time.
  if (url.hostname.endsWith("kakaocdn.net") || url.hostname === "dapi.kakao.com") {
    e.respondWith((async () => {
      const cache = await caches.open(EXT_CACHE);
      const hit = await cache.match(req);
      if (hit) {
        // Refresh the unversioned SDK for the next visit without
        // delaying this one.
        if (url.hostname === "dapi.kakao.com") {
          e.waitUntil(fetch(req).then((res) =>
            (res.ok || res.type === "opaque") ? cache.put(req, res.clone()) : undefined
          ).catch(() => {}));
        }
        return hit;
      }
      const res = await fetch(req);
      if (res.ok || res.type === "opaque") {
        e.waitUntil(cache.put(req, res.clone()).then(() => trimExt(cache)).catch(() => {}));
      }
      return res;
    })());
    return;
  }

  // Data files: network first. Complex ids are positions in complexes.json
  // and shift when a weekly update adds complexes, so a cached region or
  // trades file must never be mixed with a fresh index. The cached copy is
  // only an offline fallback.
  if (url.origin === location.origin && url.pathname.includes("/data/")) {
    e.respondWith(
      fetch(req)
        .then((r) => {
          if (r.ok) {
            const copy = r.clone();
            e.waitUntil(caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {}));
          }
          return r;
        })
        .catch(() => caches.open(CACHE).then((c) => c.match(req, { ignoreSearch: true })))
    );
    return;
  }

  // Page navigations: fresh HTML first so releases show up. Only the app
  // page itself is kept for offline use (not 404s or other pages).
  if (req.mode === "navigate") {
    const isApp = url.origin === location.origin && /\/(index\.html)?$/.test(url.pathname);
    e.respondWith(
      fetch(req)
        .then((r) => {
          if (isApp && r.ok && !r.redirected) {
            const copy = r.clone();
            e.waitUntil(caches.open(CACHE).then((c) => c.put("./", copy)).catch(() => {}));
          }
          return r;
        })
        .catch(() => caches.match("./"))
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
  // Everything else (such as Chart.js CDN) passes through.
});
