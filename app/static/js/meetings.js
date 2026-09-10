/* 회의록 목록 — 만들기 폼 접기 (UI 정리 판 2 · 3-a).
 *
 * 폼은 접힌 채 시작한다(지출의 등록 단추와 같은 부품). 값을 적기 시작했으면
 * 새로고침 전까지 펼친 채로 둔다 — 적다가 단추를 잘못 눌러 접히면 적은 것이
 * 안 보이고, 사람은 사라진 줄 안다. 저장하지 않는다. */
(function () {
  'use strict';
  var box = document.getElementById('addbox');
  if (!box) return;
  var form = box.querySelector('form');
  function filled() {
    return Array.prototype.some.call(form.querySelectorAll('input[name], textarea[name]'), function (el) {
      return el.type !== 'hidden' && el.type !== 'date' && el.value.trim() !== '';
    });
  }
  box.addEventListener('toggle', function () {
    if (!box.open && filled()) box.open = true;
  });
})();
