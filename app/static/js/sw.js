// 서비스워커 — 정적자원 캐시 + 웹 푸시 수신
//
// **미리 받아 둘 목록에 js·css 를 적지 않는다.** 그 주소에는 이제 내용 해시가
// 들어 있어서(`/static/js/app.<해시>.js`) 여기 박아 둔 이름은 배포하는 순간
// 틀린 것이 된다. 틀린 주소가 하나라도 있으면 `addAll` 이 통째로 실패하고
// **서비스워커가 설치되지 않는다** — 그러면 푸시도 함께 죽는다.
// 해시가 붙지 않는 아이콘만 미리 받고, 나머지는 아래 fetch 가 이미 받아 둔
// 것을 내주는 것으로 충분하다.
const CACHE = "dcb-v3";
const ASSETS = ["/static/icons/icon.svg"];

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

self.addEventListener("push", (event) => {
  let payload = { title: "대청부 수련회", body: "", link: "/notifications" };
  if (event.data) {
    try {
      payload = Object.assign(payload, event.data.json());
    } catch (e) {
      payload.body = event.data.text();
    }
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/static/icons/icon-192.png",
      badge: "/static/icons/icon-192.png",
      tag: payload.tag || undefined,
      data: { link: payload.link || "/notifications" },
      lang: "ko",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const link = (event.notification.data && event.notification.data.link) || "/notifications";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ("focus" in client) {
          client.navigate(link);
          return client.focus();
        }
      }
      return self.clients.openWindow(link);
    })
  );
});
