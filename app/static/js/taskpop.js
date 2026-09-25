/* 업무 팝업 (F) — **보드와 달력이 같이 쓰는 한 부품** (CLAUDE.md 4-1 · 4-13 · 목업 F).
 *
 * 담는 것이 같다(제목 전체 + 「기간 · 상태 · 담당팀」). **달력에서만** 맨 아래
 * 「상세 열기」 줄을 켠다 — 보드에는 스크롤해서 갈 자리가 있지만 달력에는 없다.
 *
 * **`data-addpop`(업무 추가 팝업)과 다른 것이다.** 저쪽은 업무를 *만드는 폼*이고
 * 여기는 이미 있는 업무를 *읽는 카드*다 — 여는 방식(누름 ↔ 호버)도, 담는 것도,
 * 서버를 부르는지도 다르다. 같은 이름을 쓰면 한쪽을 고칠 때 다른 쪽이 따라간다.
 *
 * 여는 조건(4-1): **끊긴 바 · 합친 바 · 축 상한 밖 바(`→`)**. 마지막 것은
 * 제목이 안 끊겨도 연다 — 그러지 않으면 그 업무의 실제 날짜를 말할 자리가
 * 화면 어디에도 없다.
 */
(function () {
'use strict';

let pop = null;          // 지금 떠 있는 상자
let owner = null;        // 그것을 띄운 자리
let 닫기예약 = 0;

const esc = t => String(t == null ? '' : t)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function 닫는다() {
  clearTimeout(닫기예약);
  if (pop) pop.remove();
  pop = null; owner = null;
}

/* 항목 하나 = {title, run_id, meta_line} */
function 연다(anchor, items, opts) {
  const 목록 = (items || []).filter(x => x && x.title);
  if (!목록.length) return null;
  // 같은 자리를 다시 열면 그대로 둔다 — 깜빡이면 마우스를 팝업으로 못 옮긴다
  if (pop && owner === anchor) { clearTimeout(닫기예약); return pop; }
  닫는다();

  pop = document.createElement('div');
  pop.className = 'taskpop';
  pop.innerHTML = 목록.map(x =>
    `<button type="button" class="tp" data-run="${esc(x.run_id)}">` +
      `<span class="tpt">${esc(x.title)}</span>` +
      `<span class="tpm">${esc(x.meta_line || '')}</span>` +
    `</button>`).join('')
    // **달력에서만** — 보드에는 스크롤해서 갈 자리가 있다 (4-13)
    + (opts && opts.상세열기
        ? `<button type="button" class="tpopen" data-run="${esc(목록[0].run_id)}">상세 열기</button>`
        : '');
  document.body.appendChild(pop);
  owner = anchor;

  // 대상 아래 4px (목업 F). **화면 밖으로 나가지 않는다** — 가로·세로 둘 다
  // 잡는다(한쪽만 잡으면 나머지로 넘친다 · 4-14 의 그 자리). 값은 어림이
  // 아니라 **띄운 뒤 실제 크기**로 잰다
  const r = anchor.getBoundingClientRect();
  const w = pop.offsetWidth, h = pop.offsetHeight;
  let top = r.bottom + 4;
  if (top + h > innerHeight - 8) top = Math.max(8, r.top - 4 - h);   // 위로 뒤집는다
  if (top + h > innerHeight - 8) top = Math.max(8, innerHeight - 8 - h);
  let left = Math.min(r.left, innerWidth - 8 - w);
  pop.style.top = Math.round(top) + 'px';
  pop.style.left = Math.round(Math.max(8, left)) + 'px';

  pop.addEventListener('mouseenter', () => clearTimeout(닫기예약));
  pop.addEventListener('mouseleave', () => { 닫기예약 = setTimeout(닫는다, 160); });
  pop.addEventListener('click', e => {
    const btn = e.target.closest('.tp, .tpopen');
    if (!btn) return;
    const run = btn.dataset.run;
    닫는다();
    if (run && window.Drawer) window.Drawer.open(run);
  });
  return pop;
}

/* 마우스가 대상에서 벗어났을 때 — **바로 닫지 않는다.** 팝업으로 옮기는
   사이에 닫히면 그 안의 항목을 누를 수가 없다 (목업 F) */
function 늦게닫는다() { clearTimeout(닫기예약); 닫기예약 = setTimeout(닫는다, 160); }

// 다른 곳을 누르면 닫힌다(휴대폰의 「다른 곳을 탭」 도 이 자리다).
// **팝업 안은 빼야 한다** — 안 그러면 항목을 누르는 순간 먼저 닫힌다
addEventListener('pointerdown', e => {
  if (pop && !(e.target instanceof Element && e.target.closest('.taskpop'))) 닫는다();
}, true);
addEventListener('keydown', e => { if (e.key === 'Escape') 닫는다(); });
// 스크롤하면 대상이 움직인다 — 팝업만 제자리에 남으면 엉뚱한 업무를 가리킨다
addEventListener('scroll', () => { if (pop) 닫는다(); }, true);

window.TaskPop = {open: 연다, close: 닫는다, later: 늦게닫는다,
                  get isOpen() { return !!pop; }};
})();
