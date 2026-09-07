/* 웹 푸시 구독 (4-11) — #push-card 가 있는 화면이면 어디서든 돈다.
   설정 › 내 정보와 알림 페이지가 같이 쓴다 — 한 벌이다. */

// ---------------------------------------------------------------- 서비스워커 등록
// 옛 껍데기의 app.js 가 하던 일 — 그 파일이 껍데기와 함께 사라지면서 여기로
// 왔다(단계 5). 아래 구독 코드가 serviceWorker.ready 를 기다리는데, 등록하는
// 곳이 없으면 **영영 resolve 되지 않는다** — 새 기기에서 푸시가 조용히 죽는다.
(function () {
  "use strict";
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () { /* 무시 */ });
    });
  }
})();

// ---------------------------------------------------------------- 웹 푸시 구독
(function () {
  "use strict";

  var card = document.getElementById("push-card");
  if (!card) return;

  var statusEl = document.getElementById("push-status");
  var enableBtn = document.getElementById("push-enable");
  var disableBtn = document.getElementById("push-disable");
  var testForm = document.getElementById("push-test-form");
  var vapidKey = card.dataset.vapid;

  function urlBase64ToUint8Array(base64String) {
    var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var raw = window.atob(base64);
    var output = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; ++i) output[i] = raw.charCodeAt(i);
    return output;
  }

  function show(message, opts) {
    opts = opts || {};
    statusEl.textContent = message;
    enableBtn.hidden = !opts.canEnable;
    disableBtn.hidden = !opts.canDisable;
    testForm.hidden = !opts.canTest;
  }

  var supported =
    "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

  if (!supported) {
    show("이 브라우저는 웹 푸시를 지원하지 않습니다. 알림함에서 확인해주세요.");
    return;
  }
  // 웹 푸시는 브라우저 규격상 HTTPS 또는 localhost 에서만 동작한다
  if (!window.isSecureContext) {
    show("푸시 알림은 HTTPS 또는 localhost 접속에서만 켤 수 있습니다. 알림함에서는 정상적으로 확인됩니다.");
    return;
  }

  // serviceWorker.ready 는 등록된 워커가 없으면 **영영 resolve 되지 않는다.**
  // 그대로 두면 화면이 "확인 중…" 에서 멈춘 채로 남는다 — 실패했다는 것도
  // 알려주지 못하는 상태가 가장 나쁘다.
  function readyOrGiveUp() {
    return Promise.race([
      navigator.serviceWorker.ready,
      new Promise(function (_resolve, reject) {
        setTimeout(function () { reject(new Error("sw-timeout")); }, 4000);
      }),
    ]);
  }

  function refresh() {
    readyOrGiveUp()
      .then(function (reg) {
        return reg.pushManager.getSubscription();
      })
      .then(function (sub) {
        if (Notification.permission === "denied") {
          show("브라우저에서 알림이 차단되어 있습니다. 사이트 설정에서 허용해주세요.");
          return;
        }
        if (sub) {
          show("이 기기에서 푸시 알림을 받고 있습니다.", { canDisable: true, canTest: true });
        } else {
          show("이 기기는 아직 푸시 알림을 받지 않습니다.", { canEnable: true });
        }
      })
      .catch(function () {
        show("이 브라우저에서 알림을 준비하지 못했습니다. 새로고침하거나 다른 브라우저에서 켜보세요.");
      });
  }

  enableBtn.addEventListener("click", function () {
    enableBtn.disabled = true;
    Notification.requestPermission()
      .then(function (permission) {
        if (permission !== "granted") throw new Error("permission");
      })
      .then(function () {
        return readyOrGiveUp();
      })
      .then(function (reg) {
        return reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidKey),
        });
      })
      .then(function (sub) {
        return fetch("/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subscription: sub.toJSON() }),
        });
      })
      .then(refresh)
      .catch(function () {
        show("알림을 켜지 못했습니다. 브라우저 알림 권한을 확인해주세요.", { canEnable: true });
      })
      .finally(function () {
        enableBtn.disabled = false;
      });
  });

  disableBtn.addEventListener("click", function () {
    navigator.serviceWorker.ready
      .then(function (reg) {
        return reg.pushManager.getSubscription();
      })
      .then(function (sub) {
        if (!sub) return null;
        var endpoint = sub.endpoint;
        return sub.unsubscribe().then(function () {
          return fetch("/push/unsubscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint: endpoint }),
          });
        });
      })
      .then(refresh)
      .catch(refresh);
  });

  refresh();
})();
