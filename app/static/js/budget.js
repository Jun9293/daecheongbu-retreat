/* 예산 (CLAUDE.md 7-3) — 단가 × 명수 × 횟수를 **그 자리에서** 계산해 보여준다.
 *
 * 저장 전에는 DB 를 건드리지 않는다 — 셋이 다 차면 예산금액 칸을 계산값으로
 * 채우고 잠그듯 보여주며, 하나라도 비우면 직접 입력으로 돌아간다.
 * 저장할 때 같은 계산을 서버(domain.budget.planned_amount_of)가 다시 한다 —
 * 화면의 계산은 미리보기지 정본이 아니다. */
(function () {
  'use strict';

  function wire(form) {
    var unit = form.querySelector('[data-calc="unit"]');
    var head = form.querySelector('[data-calc="head"]');
    var times = form.querySelector('[data-calc="times"]');
    var planned = form.querySelector('[data-calc="planned"]');
    var note = form.querySelector('[data-calc="note"]');
    if (!unit || !head || !times || !planned) return;

    function refresh() {
      var u = unit.value.trim(), h = head.value.trim(), t = times.value.trim();
      if (u !== '' && h !== '' && t !== '') {
        var value = (parseInt(u, 10) || 0) * (parseInt(h, 10) || 0) * (parseInt(t, 10) || 0);
        planned.value = value;
        planned.readOnly = true;
        if (note) note.textContent = '= ' + value.toLocaleString('ko-KR') + '원 (단가 × 명수 × 횟수)';
      } else {
        planned.readOnly = false;
        if (note) note.textContent = '';
      }
    }

    [unit, head, times].forEach(function (el) {
      el.addEventListener('input', refresh);
    });
    refresh();
  }

  document.querySelectorAll('form.editform').forEach(wire);
})();
