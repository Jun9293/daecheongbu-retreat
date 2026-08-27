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

    if (!amount || !head) {
      preview.textContent = "인원수와 금액을 입력하면 지원금액이 자동 계산됩니다.";
      return;
    }
    preview.innerHTML =
      "지원금액 <b>" + formatWon(subsidy) + "</b> · 개인부담 <b>" + formatWon(burden) + "</b>" +
      '<div class="tiny">min(' + formatWon(amount) + ", " + head + "명 × " + formatWon(cap) + ")";
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
