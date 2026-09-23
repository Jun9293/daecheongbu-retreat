/* 기간을 고르는 달력 팝업 — **드로어 밖에서도 부른다** (CLAUDE.md 4-9 · 목업 B).
 *
 * 드로어의 기간 줄이 이것을 쓰고, 업무 추가 팝업(6-7)도 **같은 부품**을 씁니다.
 * 두 벌이 되면 고르는 차례(시작 → 마감 → 다시 시작)와 맞바꿈이 두 곳에서
 * 갈리고, **갈린 쪽을 아무도 눈치채지 못합니다** — 이 저장소가 가장 자주
 * 고쳐 온 모양입니다. 그래서 파일을 따로 두고 `window.DatePick` 하나로 냅니다.
 *
 *     DatePick.open(anchor, {start, end, onSave(start, end)});
 *
 * `onSave` 는 **저장에 성공했을 때만** 참을 돌려줍니다(또는 그런 Promise).
 * 거짓이면 팝업을 안 닫고 그 자리에 까닭을 냅니다 — 조용히 닫으면 고친 줄
 * 알고 넘어갑니다(5-0 과 같은 자리).
 *
 * **공휴일은 아직 비어 있습니다.** 표는 도메인 한 곳에 두기로 했고(4-13)
 * 그것을 세우는 것은 달력 단계입니다 — 여기서 목록을 따로 만들면 두 벌이
 * 됩니다. 그때까지 일요일만 붉고, `공휴일` 로 받는 자리만 만들어 둡니다.
 */
(function () {
'use strict';

const WD = ['일', '월', '화', '수', '목', '금', '토'];
const 하루 = 864e5;   // 86,400,000ms

const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const 점 = s => s ? s.replaceAll('-', '.') : '';

/* 며칠짜리인가 — 드로어의 `spanLabel` 과 같은 셈이다 */
function 날수(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 하루) + 1;
}

let box = null, 상태 = null;

function 닫는다() {
  if (box) { box.remove(); box = null; }
  상태 = null;
  removeEventListener('pointerdown', 밖을눌렀나, true);
  removeEventListener('keydown', 키);
  removeEventListener('scroll', 밀렸다, true);
  removeEventListener('resize', 밀렸다);
}

function 밖을눌렀나(e) {
  if (box && e.target instanceof Element && !box.contains(e.target)
      && e.target !== 상태.anchor && !상태.anchor.contains(e.target)) 닫는다();
}
function 키(e) { if (e.key === 'Escape') 닫는다(); }

/* 안내 줄 — 고른 만큼만 말한다 (목업 B 의 세 줄) */
function 안내() {
  const {start, end} = 상태;
  if (!start) return '시작일을 누르세요.';
  if (!end) return '마감일을 누르세요 — 같은 날을 한 번 더 누르면 하루 업무입니다.';
  return start === end
    ? `${점(start)} 하루 업무`
    : `${점(start)} – ${점(end)} · ${날수(start, end)}일간 기간 업무`;
}

function 그린다() {
  const {달, start, end} = 상태;
  const 첫날 = new Date(달.getFullYear(), 달.getMonth(), 1);
  const 앞 = 첫날.getDay();
  const 날수달 = new Date(달.getFullYear(), 달.getMonth() + 1, 0).getDate();
  let 칸 = '';
  for (let i = 0; i < 앞; i++) 칸 += '<i class="pad"></i>';
  for (let d = 1; d <= 날수달; d++) {
    // **한 함수 안에서 해석을 갈지 않는다.** `new Date('2026-05-17')` 은 UTC 로
    // 읽히고 `new Date(y, m, d)` 는 지역이라, 칸 자리와 「일요일인가」 가 서로
    // 다른 규칙으로 셈되고 있었다 — KST 에서는 결과가 같아 안 드러난다
    const 날 = new Date(달.getFullYear(), 달.getMonth(), d);
    const v = iso(날);
    const wd = 날.getDay();
    const 빨강 = wd === 0 || 상태.공휴일.includes(v);
    const 끝 = v === start || v === end;
    const 사이 = start && end && v > start && v < end;
    칸 += `<button type="button" data-d="${v}" class="${끝 ? 'edge' : ''}${사이 ? ' mid' : ''}${빨강 ? ' red' : ''}">${d}</button>`;
  }
  box.querySelector('.dpgrid').innerHTML = 칸;
  box.querySelector('.dpmon').textContent = `${달.getFullYear()}년 ${달.getMonth() + 1}월`;
  box.querySelector('.dphint').textContent = 안내();
  box.querySelector('.dpsave').disabled = !start;
}

/* 누른 날 — 시작만 있으면 마감, 둘 다 있으면 **시작부터 다시**,
   시작보다 앞이면 맞바꾼다 (목업 B) */
function 날을눌렀다(v) {
  const {start, end} = 상태;
  if (!start || (start && end)) { 상태.start = v; 상태.end = ''; }
  else if (v < start) { 상태.end = start; 상태.start = v; }
  else { 상태.end = v; }
  그린다();
}

function open(anchor, opts) {
  닫는다();
  const o = opts || {};
  상태 = {
    anchor,
    start: o.start || '',
    end: o.end || o.start || '',
    공휴일: o.공휴일 || [],
    onSave: o.onSave,
    달: new Date((o.start || iso(new Date())) + 'T00:00:00'),
  };
  box = document.createElement('div');
  box.className = 'datepick';
  box.innerHTML =
    `<div class="dpbar"><button type="button" class="dpprev" aria-label="지난 달">‹</button>
       <b class="dpmon"></b><button type="button" class="dpnext" aria-label="다음 달">›</button></div>
     <div class="dpwd">${WD.map(w => `<i>${w}</i>`).join('')}</div>
     <div class="dpgrid"></div>
     <p class="dphint"></p>
     <p class="dperr" hidden></p>
     <div class="dpfoot"><button type="button" class="dpcancel">취소</button>
       <button type="button" class="dpsave pri">저장</button></div>`;
  document.body.appendChild(box);
  자리를잡는다(anchor);
  그린다();

  box.querySelector('.dpprev').onclick = () => { 상태.달.setMonth(상태.달.getMonth() - 1); 그린다(); };
  box.querySelector('.dpnext').onclick = () => { 상태.달.setMonth(상태.달.getMonth() + 1); 그린다(); };
  box.querySelector('.dpgrid').onclick = e => {
    const b = e.target.closest('button[data-d]');
    if (b) 날을눌렀다(b.dataset.d);
  };
  box.querySelector('.dpcancel').onclick = 닫는다;
  box.querySelector('.dpsave').onclick = async () => {
    if (!상태.start) return;
    const {start} = 상태, end = 상태.end || 상태.start;
    const save = 상태.onSave;
    const err = box.querySelector('.dperr');
    const btn = box.querySelector('.dpsave');
    btn.disabled = true;                       // 저장 중에는 다시 못 누른다
    let 됐나 = true;
    try { if (save) 됐나 = await save(start, end); } catch (e) { 됐나 = false; }
    // **실패하면 안 닫는다** — 닫으면 고쳐진 줄 알고 넘어간다
    if (됐나 === false) {
      if (box) { err.hidden = false; err.textContent = '저장하지 못했습니다 — 다시 눌러 주세요.'; btn.disabled = false; }
      return;
    }
    닫는다();
  };

  addEventListener('pointerdown', 밖을눌렀나, true);
  addEventListener('keydown', 키);
  // **스크롤하거나 창 크기가 바뀌면 닫는다** — 목록의 상태 메뉴와 같은 규약의
  // 나머지 절반이다(4-14). `position:fixed` 라 안 닫으면 팝업만 제자리에 남고,
  // 목록에서는 행 안의 드로어와 함께 페이지가 스크롤하므로 **엉뚱한 자리에서
  // 날짜를 고치게 된다.** 처음에는 「화면 밖으로 안 나간다」 만 가져왔다(검토가 잡음)
  addEventListener('scroll', 밀렸다, true);
  addEventListener('resize', 밀렸다);
}

/* 스크롤·창 크기가 바뀌면 닫는다 (4-14 의 그 규약). 고르던 것은 버린다 —
   저장을 안 눌렀으면 아직 아무것도 안 바뀐 것이다 */
function 밀렸다() { 닫는다(); }

/* 화면 밖으로 나가지 않는다 — 목록의 상태 메뉴와 같은 규약(4-14).
   `position:fixed` 라 가로·세로 둘 다 잡는다. 값은 어림이 아니라 띄운 뒤 실제 크기로. */
function 자리를잡는다(anchor) {
  const r = anchor.getBoundingClientRect();
  const w = box.offsetWidth, h = box.offsetHeight;
  let top = r.bottom + 6, left = r.left;
  if (top + h > innerHeight - 8) top = Math.max(8, r.top - h - 6);
  if (left + w > innerWidth - 8) left = Math.max(8, innerWidth - w - 8);
  box.style.top = top + 'px';
  box.style.left = left + 'px';
}

window.DatePick = {open, close: 닫는다, isOpen: () => !!box};
})();
