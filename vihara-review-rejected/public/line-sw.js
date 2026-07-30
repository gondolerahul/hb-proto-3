/**
 * The Line's service worker (LINE L5). Three duties, deliberately no more:
 *
 * 1. `push` — the payload is `{tray_id, one_sentence}` and NOTHING else
 *    (L8 made richer pushes unimplementable server-side; the worker
 *    matches that shape and invents nothing).
 * 2. `notificationclick` — focus the Line, or open it at the tray.
 * 3. A small offline shell cache, network-first — the Line degrades to
 *    the last shell, never to a dinosaur.
 *
 * There is NO background sync and NO offline queue: an offline approval
 * would be a certified act with no server, which must not exist.
 */
const SHELL_CACHE = "line-shell-v1";
const SHELL_URLS = ["/line.html", "/line.webmanifest", "/line-icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("line-shell-") && key !== SHELL_CACHE)
          .map((key) => caches.delete(key)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Only the shell is cached — API responses are never served stale.
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) {
    return;
  }
  if (!SHELL_URLS.includes(url.pathname)) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(SHELL_CACHE).then((cache) => {
          cache.put(event.request, copy);
        });
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});

self.addEventListener("push", (event) => {
  let payload = { tray_id: null, one_sentence: "A decision is waiting for you." };
  try {
    payload = { ...payload, ...event.data.json() };
  } catch (_error) {
    // A malformed push still says something true.
  }
  event.waitUntil(
    self.registration.showNotification("The Line", {
      body: payload.one_sentence,
      tag: payload.tray_id || "line-tray",
      icon: "/line-icon.svg",
      data: { tray_id: payload.tray_id },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = "/line.html#thread";
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          if (client.url.includes("/line.html") && "focus" in client) {
            return client.focus();
          }
        }
        return self.clients.openWindow(target);
      }),
  );
});
