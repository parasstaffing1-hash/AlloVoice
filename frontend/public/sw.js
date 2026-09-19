const CACHE_VERSION = 3;
const STATIC_CACHE = `voicefield-static-v${CACHE_VERSION}`;
const API_CACHE = `voicefield-api-v${CACHE_VERSION}`;
const OFFLINE_PAGE = "/offline";

const STATIC_ASSETS = ["/", "/offline"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter(
            (key) =>
              key !== STATIC_CACHE &&
              key !== API_CACHE
          )
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== "GET") {
    // Queue non-GET requests (mutations) for background sync
    if (url.pathname.startsWith("/api/")) {
      event.respondWith(networkFirstWithFallback(request));
    }
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // API requests: network-first with IndexedDB fallback
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }

  // Everything else: network-first, fall back to cache
  event.respondWith(networkFirst(request));
});

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return caches.match(OFFLINE_PAGE);
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || caches.match(OFFLINE_PAGE);
  }
}

async function networkFirstWithFallback(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: "offline" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }
}

// Background sync via message from main thread
self.addEventListener("message", (event) => {
  if (event.data?.type === "SYNC_QUEUED") {
    event.waitUntil(
      self.registration.sync?.register("voicefield-sync").catch(() => {})
    );
  }
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("sync", (event) => {
  if (event.tag === "voicefield-sync") {
    event.waitUntil(syncPendingOps());
  }
});

async function syncPendingOps() {
  // Notify clients to run their own sync
  const clients = await self.clients.matchAll();
  for (const client of clients) {
    client.postMessage({ type: "TRIGGER_SYNC" });
  }
}
