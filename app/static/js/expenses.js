/* 지출 (CLAUDE.md 7-2) — 식대 입력 미리보기.
 *
 * 인원수·금액을 넣으면 지원금액 = min(금액, 인원 × 상한)이 그 자리에서
 * 보인다. 정본 계산은 서버(domain.meal.calculate_meal_settlement)다 —
 * 화면의 것은 미리보기라 저장 전엔 아무것도 안 바꾼다.
 * (옛 껍데기의 app.js 에서 옮겨 왔다 — 그 파일은 껍데기와 함께 지웠다.) */
(function () {
  'use strict';

  var toggle = document.getElementById('meal-toggle');
  var fields = document.getElementById('meal-fields');
  var amountInput = document.getElementById('e-amount');
  var headInput = document.getElementById('e-head');
  var attInput = document.getElementById('e-att');
  var preview = document.getElementById('meal-preview');
  var attCount = document.getElementById('att-count');

  function formatWon(n) {
    return n.toLocaleString('ko-KR') + '원';
  }

  function countNames(text) {
    if (!text) return 0;
    return text.split(/[,\n\r\t ]+/).filter(function (s) { return s.length > 0; }).length;
  }

  function updatePreview() {
    if (!toggle || !toggle.checked || !preview) return;
    var cap = parseInt(toggle.dataset.cap || '0', 10);
    var amount = parseInt((amountInput && amountInput.value) || '0', 10) || 0;
    var head = parseInt((headInput && headInput.value) || '0', 10) || 0;
    var subsidy = Math.min(amount, head * cap);
    var burden = amount - subsidy;

    var slot = preview.querySelector('span') || preview;
    if (!amount || !head) {
      slot.textContent = '인원수와 금액을 입력하면 지원금액이 자동 계산됩니다.';
      preview.classList.remove('warn');
      return;
    }
    slot.innerHTML =
      '지원금액 <b>' + formatWon(subsidy) + '</b> · 개인부담 <b>' + formatWon(burden) + '</b>' +
      ' <small>min(' + formatWon(amount) + ', ' + head + '명 × ' + formatWon(cap) + ')</small>';
    preview.classList.toggle('warn', burden > 0);
  }

  function updateAttCount() {
    if (!attCount || !attInput) return;
    var n = countNames(attInput.value);
    attCount.textContent = n ? '명단 ' + n + '명 입력됨' : '';
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
    toggle.addEventListener('change', syncMealFields);
    syncMealFields();
  }
  [amountInput, headInput].forEach(function (el) {
    if (el) el.addEventListener('input', updatePreview);
  });
  if (attInput) attInput.addEventListener('input', updateAttCount);
})();
