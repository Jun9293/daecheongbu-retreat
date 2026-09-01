/* 달력 보기 (CLAUDE.md 4-13) — 점을 누르면 **그 자리에서** 상세 패널이 열린다.
 *
 * 전에는 `/board?task=` 로 넘겨 보냈다. 그러면 보던 달과 범위 칩을 잃고,
 * 돌아오려면 뒤로 가야 했다. 그렇다고 패널을 한 벌 더 만들 수는 없어서
 * (논의·상태·첨부·선후행이 두 곳에서 갈린다) **패널은 보드와 같은 것을 쓰고**
 * 여기서는 "달력은 이렇게 고쳐 그린다" 만 알려 준다.
 *
 *   화면  templates/partials/drawer.html   ← 보드와 공용
 *   코드  static/js/drawer.js              ← 보드와 공용
 *
 * **다시 불러오지 않는다.** 보던 달·범위 칩·`미완료만` 을 잃으면, 담당자가
 * "이번 주에 내가 뭘 해야 하나" 를 보려고 연 화면이 매번 처음으로 돌아간다.
 */
(function () {
'use strict';

const bar = document.querySelector('.calbar');
const note = document.getElementById('calnote');

/* 값은 구조가 실어 보낸 것을 읽는다. 칩의 클래스나 주소를 뒤져 알아내면
   범위 칩과 헷갈려 조용히 반대로 판단한다.
   **`.calbar` 가 없어도 죽지 않는다** — 이 파일은 패널이 있는 화면이면
   어디서든 실릴 수 있고, 그때 상태 변경이 통째로 멈추면 안 된다. */
const onlyOpen = () => bar?.dataset.onlyOpen === '1';
const todayIso = () => bar?.dataset.today || '';
const perDay = () => Number(bar?.dataset.perDay) || 3;

const dots = runId => [...document.querySelectorAll(`.cal-dot[data-run="${runId}"]`)];

/* 같은 업무가 여러 곳에 있다 — 월 격자, 좁은 화면의 주 목록, 그리고
   `외 N건` 안. 하나만 고치면 화면을 넓혔다 좁혔을 때 어긋난다. */
function titleOf(runId) {
  const one = dots(runId)[0];
  const label = one && one.querySelector('.cal-t');
  return label ? label.textContent.trim() : '';
}

function say(text) {
  if (!note) return;
  note.textContent = text || '';
  note.hidden = !text;
}

/* ── 상태가 바뀌면 점을 다시 칠한다 ─────────────────────────────────── */
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

/* ── 마감일이 바뀌면 점이 그 날로 옮겨간다 ───────────────────────────
   달력에서 점의 자리를 정하는 것은 **마감일**이다 (4-13). 패널에서 기간을
   고쳤는데 점이 옛 칸에 그대로 있으면, 한 화면이 서로 다른 날짜를 말한다. */
function applyDates(runId, saved) {
  const iso = saved.end || saved.start;
  if (!iso) return;

  const existing = dots(runId);
  if (!existing.length) return;
  const model = existing[0].cloneNode(true);
  existing.forEach(el => el.remove());

  // 기한 초과도 날짜가 정한다 — 옮기면서 함께 다시 본다
  const today = todayIso();
  const overdue = !!today && iso < today && !model.classList.contains('done');
  model.dataset.overdue = overdue ? '1' : '0';
  model.classList.toggle('late', overdue);

  const cell = document.querySelector(`.cal-cell[data-date="${iso}"]:not(.out)`);
  if (cell) {
    placeInGrid(cell, model);
    placeInWeekList(iso, model.cloneNode(true));
    say('');
  } else {
    // **조용히 사라지면 "지워진 건가" 로 읽힌다.** 어디로 갔는지 말해 준다.
    const title = model.querySelector('.cal-t');
    // 조사는 붙여 쓴다 — "방명록 의" 가 아니라 "방명록의"
    say(`${title ? title.textContent.trim() + '의 ' : ''}마감일이 ${iso} 로 바뀌어 `
      + '이 달에는 보이지 않습니다. 그 달로 넘겨서 보세요.');
  }
  recount();
}

/* 한 칸에 `per_day` 개까지만 펼치고 나머지는 `외 N건` 안에 넣는다 (4-13).
   다 펼치면 그 주만 세로로 길어져 달력으로 읽히지 않는다. */
function placeInGrid(cell, dot) {
  const open = [...cell.children].filter(el => el.classList.contains('cal-dot'));
  let more = cell.querySelector('.cal-more');
  if (open.length < perDay()) {
    if (more) more.before(dot); else cell.appendChild(dot);
    return;
  }
  if (!more) {
    more = document.createElement('details');
    more.className = 'cal-more';
    more.innerHTML = '<summary></summary>';
    cell.appendChild(more);
  }
  more.appendChild(dot);
}

/* 좁은 화면의 주 목록. **그 날 줄이 아직 없으면 만든다** — 목록은 점이 있는
   날만 그리므로, 옮겨온 날이 원래 비어 있었으면 놓을 자리가 없다. */
function placeInWeekList(iso, dot) {
  const list = document.querySelector('.calweeks');
  if (!list) return;
  let day = list.querySelector(`.calday[data-date="${iso}"]`);
  if (!day) {
    const week = [...list.querySelectorAll('.calweek')].find(
      s => s.dataset.from <= iso && iso <= s.dataset.to);
    if (!week) return;                    // 이 달의 주 목록 밖이면 놓지 않는다
    day = document.createElement('div');
    day.className = 'calday';
    day.dataset.date = iso;
    const num = Number(iso.slice(8, 10));
    day.innerHTML = `<span class="calday-d">${num}</span><div class="calday-l"></div>`;
    const after = [...week.querySelectorAll('.calday')].find(d => d.dataset.date > iso);
    if (after) after.before(day); else week.appendChild(day);
    week.hidden = false;
  }
  day.querySelector('.calday-l').appendChild(dot);
}

/* 숫자를 화면과 맞춘다 — `외 N건` · `날짜가 없는 업무 N건` · 위쪽의 건수.
   **세어서 다시 적는다.** 더하고 빼면 한 번 어긋난 뒤로 영영 어긋난다. */
function recount() {
  document.querySelectorAll('.cal-more').forEach(more => {
    const n = more.querySelectorAll('.cal-dot').length;
    if (!n) { more.remove(); return; }
    more.querySelector('summary').textContent = `외 ${n}건`;
  });
  document.querySelectorAll('.calweeks .calday').forEach(day => {
    if (!day.querySelectorAll('.cal-dot').length) day.remove();
  });
  document.querySelectorAll('.calweeks .calweek').forEach(week => {
    week.hidden = !week.querySelectorAll('.cal-dot').length;
  });

  const undated = document.querySelector('.calundated');
  if (undated) {
    const n = undated.querySelectorAll('.cal-dot').length;
    if (!n) undated.remove();
    else undated.querySelector('summary').textContent = `날짜가 없는 업무 ${n}건`;
  }

  const count = document.querySelector('.calcount');
  if (count) {
    const grid = document.querySelector('.cal-grid');
    const seen = new Set();
    if (grid) {
      grid.querySelectorAll('.cal-cell:not(.out) .cal-dot').forEach(
        d => seen.add(d.dataset.run));
    }
    count.textContent = `${seen.size}건`;
  }
}

Drawer.init({
  // 달력에는 스크롤해서 갈 자리가 없다 — '이동' 메뉴를 내지 않는다
  canGoTo: false,
  // 이 달에 없는 업무도 열 수 있어야 한다 (`/calendar?task=123`).
  // 그래서 못 찾아도 null 이 아니라 빈 것을 준다 — 제목만 잠깐 비고,
  // 나머지는 서버에서 받아 채운다.
  meta: runId => ({title: titleOf(runId)}),
  onStatus: applyStatus,
  onDates: applyDates,
  isTaskClick: el => el.closest('.cal-dot'),

  /* ── 일부러 등록하지 않은 것 ──────────────────────────────────────
     빠뜨린 것과 구별되도록 여기 적는다. `call()` 은 없는 핸들러를 조용히
     건너뛰므로, 적어 두지 않으면 화면만 봐서는 둘을 가릴 수 없다.
     `tests/test_calendar.py` 가 이 목록과 실제 등록을 대조한다. */
  __unused: {
    goTo: '달력에는 스크롤해서 갈 자리가 없다. canGoTo:false 라 불리지도 않는다',
    link: '연결 강조는 보드의 바 사이에 선을 긋는 것이다. 점에는 그을 선이 없다',
    afterLayout: '다시 그릴 것이 없다. 달력은 서버가 그린 표 그대로다',
    onOpen: '패널이 열릴 때 달력이 따로 할 일이 없다',
    onClose: '닫을 때도 마찬가지다. 보드는 연결 강조를 지우지만 달력엔 없다',
    onAssignee: '담당자는 점에 적히지 않는다. 마우스를 올렸을 때 뜨는 설명뿐이라 그대로 둔다',
    onDepartment: '담당팀을 옮기면 부서 색이 바뀌는데, 그건 통째로 다시 그리는 것이 맞다. 기본값(새로고침)을 쓴다',
    openFromUrl: '`?task=` 로 들어오면 그냥 열면 된다. 보드처럼 스크롤해서 옮길 자리가 없다',
  },
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
