// 서비스워커 — Phase 1은 오프라인 정적자원 캐시까지만.
// Phase 2에서 웹 푸시(push/notificationclick) 처리를 여기에 추가한다.
const CACHE = "dcb-v1";
const ASSETS = ["/static/css/app.css", "/static/js/app.js", "/static/icons/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || !url.pathname.startsWith("/static/")) return;
  event.respondWith(caches.match(event.request).then((hit) => hit || fetch(event.request)));
});
