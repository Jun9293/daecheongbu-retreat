// 대청부 수련회 관리 시스템 — 최소한의 클라이언트 스크립트
(function () {
  "use strict";

  // 1) 식대 입력 폼: 인원수/금액 입력 즉시 지원금액·개인부담액 미리보기
  var toggle = document.getElementById("meal-toggle");
  var fields = document.getElementById("meal-fields");
  var amountInput = document.getElementById("e-amount");
  var headInput = document.getElementById("e-head");
  var attInput = document.getElementById("e-att");
  var preview = document.getElementById("meal-preview");
  var attCount = document.getElementById("att-count");

  function formatWon(n) {
    return n.toLocaleString("ko-KR") + "원";
  }

  function countNames(text) {
    if (!text) return 0;
    return text.split(/[,\n\r\t ]+/).filter(function (s) { return s.length > 0; }).length;
  }

  function updatePreview() {
    if (!toggle || !toggle.checked || !preview) return;
    var cap = parseInt(toggle.dataset.cap || "0", 10);
    var amount = parseInt((amountInput && amountInput.value) || "0", 10) || 0;
    var head = parseInt((headInput && headInput.value) || "0", 10) || 0;
    var subsidy = Math.min(amount, head * cap);
    var burden = amount - subsidy;

    // 배너 안의 텍스트 영역만 갈아끼운다 (아이콘은 유지)
    var slot = preview.querySelector("span") || preview;
    if (!amount || !head) {
      slot.textContent = "인원수와 금액을 입력하면 지원금액이 자동 계산됩니다.";
      preview.className = "banner banner-info";
      return;
    }
    slot.innerHTML =
      "지원금액 <b>" + formatWon(subsidy) + "</b> · 개인부담 <b>" + formatWon(burden) + "</b>" +
      '<br><span class="tiny">min(' + formatWon(amount) + ", " + head + "명 × " + formatWon(cap) + ")</span>";
    preview.className = burden > 0 ? "banner banner-warn" : "banner banner-ok";
  }

  function updateAttCount() {
    if (!attCount || !attInput) return;
    var n = countNames(attInput.value);
    attCount.textContent = n ? "명단 " + n + "명 입력됨" : "";
    // 명단을 적었는데 인원수가 비어 있으면 자동으로 채워준다
    if (n && headInput && !headInput.value) {
      headInput.value = n;
      updatePreview();
    }
  }

  function syncMealFields() {
    if (!toggle || !fields) return;
    fields.hidden = !toggle.checked;
    updatePreview();
  }

  if (toggle) {
    toggle.addEventListener("change", syncMealFields);
    syncMealFields();
  }
  [amountInput, headInput].forEach(function (el) {
    if (el) el.addEventListener("input", updatePreview);
  });
  if (attInput) attInput.addEventListener("input", updateAttCount);

  // 2) 안내 배너는 4초 뒤 사라지게
  var flash = document.querySelector(".flash");
  if (flash) {
    setTimeout(function () {
      flash.style.transition = "opacity .4s";
      flash.style.opacity = "0";
      setTimeout(function () { flash.remove(); }, 400);
    }, 4000);
  }

  // 3) PWA 서비스워커 등록 (Phase 2의 웹 푸시 기반)
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

  function refresh() {
    navigator.serviceWorker.ready
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
        show("푸시 상태를 확인하지 못했습니다.", { canEnable: true });
      });
  }

  enableBtn.addEventListener("click", function () {
    enableBtn.disabled = true;
    Notification.requestPermission()
      .then(function (permission) {
        if (permission !== "granted") throw new Error("permission");
        return navigator.serviceWorker.ready;
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

// ---------------------------------------------------------------- 목록 좁히기
// 선행 작업처럼 항목이 많은 선택 목록을 이름으로 필터링한다.
(function () {
  "use strict";
  document.querySelectorAll("input[data-filter]").forEach(function (input) {
    var list = document.querySelector(input.dataset.filter);
    if (!list) return;
    var rows = Array.prototype.slice.call(list.querySelectorAll("[data-text]"));
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      rows.forEach(function (row) {
        row.hidden = q !== "" && row.dataset.text.toLowerCase().indexOf(q) === -1;
      });
    });
  });
})();
