/* 달력 보기 (CLAUDE.md 4-13) — 점을 누르면 **그 자리에서** 상세 패널이 열린다.
 *
 * 전에는 `/board?task=` 로 넘겨 보냈다. 그러면 보던 달과 범위 칩을 잃고,
 * 돌아오려면 뒤로 가야 했다. 그렇다고 패널을 한 벌 더 만들 수는 없어서
 * (논의·상태·첨부·선후행이 두 곳에서 갈린다) **패널은 보드와 같은 것을 쓰고**
 * 여기서는 "달력은 이렇게 고쳐 그린다" 만 알려 준다.
 *
 *   화면  templates/partials/drawer.html   ← 보드와 공용
 *   코드  static/js/drawer.js              ← 보드와 공용
 */
(function () {
'use strict';

const dots = runId => [...document.querySelectorAll(`.cal-dot[data-run="${runId}"]`)];

/* 같은 업무가 여러 곳에 있다 — 월 격자, 좁은 화면의 주 목록, 그리고
   `외 N건` 안. 하나만 고치면 화면을 넓혔다 좁혔을 때 어긋난다. */
function titleOf(runId) {
  const one = dots(runId)[0];
  const label = one && one.querySelector('.cal-t');
  return label ? label.textContent.trim() : '';
}

/* '미완료만' 이 켜져 있으면 완료된 것은 목록에서 빠진다 — 보드가 하는 것과
   같다. 두 화면이 같은 말("미완료만")로 다르게 굴면 어느 쪽이 맞는지
   알 수 없어진다.

   **값은 구조가 실어 보낸 것을 읽는다.** 칩의 클래스나 주소를 뒤져
   알아내면 범위 칩과 헷갈려 조용히 반대로 판단한다. */
const onlyOpen = () => document.querySelector('.calbar').dataset.onlyOpen === '1';

function applyStatus(runId, status, view) {
  const hide = onlyOpen() && status === '완료';
  dots(runId).forEach(dot => {
    dot.style.background = view.background;
    dot.style.borderColor = view.border;
    dot.classList.toggle('done', status === '완료');
    // 기한 초과는 **날짜에서 계산한 것**이다 (4-10). 구조가 실어 보낸 값을
    // 그대로 쓰되, 완료되면 더 이상 초과가 아니다.
    dot.classList.toggle('late', dot.dataset.overdue === '1' && status !== '완료');
    dot.classList.toggle('filtered', hide);
  });
}

Drawer.init({
  // 달력에는 스크롤해서 갈 자리가 없다 — '이동' 메뉴를 내지 않는다
  canGoTo: false,
  // 이 달에 없는 업무도 열 수 있어야 한다 (`/calendar?task=123`).
  // 그래서 못 찾아도 null 이 아니라 빈 것을 준다 — 제목만 잠깐 비고,
  // 나머지는 서버에서 받아 채운다.
  meta: runId => ({title: titleOf(runId)}),
  onStatus: applyStatus,
  isTaskClick: el => el.closest('.cal-dot'),
});

/* 점을 누르면 패널이 열린다. `href` 는 그대로 두었다 —
   자바스크립트가 죽었거나 가운데 버튼으로 누르면 보드로 가는 길이 남는다. */
document.addEventListener('click', e => {
  const dot = e.target.closest('.cal-dot[data-run]');
  if (!dot) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;   // 새 탭으로 여는 길은 막지 않는다
  e.preventDefault();
  Drawer.open(dot.dataset.run);
});
})();
