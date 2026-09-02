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
const perDay = () => Number(bar?.dataset.perDay) || 3;

const dots = runId => [...document.querySelectorAll(`.cal-dot[data-run="${runId}"]`)];

/* 같은 업무가 여러 곳에 있다 — 월 격자, 좁은 화면의 주 목록, 그리고
   `외 N건` 안. 하나만 고치면 화면을 넓혔다 좁혔을 때 어긋난다. */
function titleOf(runId) {
  const one = dots(runId)[0];
  const label = one && one.querySelector('.cal-t');
  return label ? label.textContent.trim() : '';
}

function say(text, runId) {
  if (!note) return;
  note.textContent = text || '';
  note.hidden = !text;
  // 누구에 대한 말인지 기억해 둔다 — 그 업무가 되돌아왔을 때만 지우기 위해서다
  if (text) note.dataset.run = String(runId ?? '');
  else delete note.dataset.run;
}

/* ── 점을 칠한다 ─────────────────────────────────────────────────────
   **색도 기한 초과도 서버가 정한 것을 그대로 쓴다** (4-13).
   화면에서 다시 계산하면 두 벌이 되고, 두 벌은 반드시 어긋난다 —
   실제로 어긋나 있었다. 마감일을 옮길 때 `iso < today` 로 초과를 다시
   판단하면서 색은 손대지 않아, **붉은 점을 미래로 옮겨도 붉게 남았다.**

   `paint` 는 `/status` 와 `/dates` 가 똑같은 모양으로 돌려준다
   (`board.paint_of`). 달력은 그중 `dot_*` 를 쓴다 — 보드의 바는 저장된
   상태 그대로 칠하지만 점은 기한이 지나면 '지연' 으로 칠하기 때문이다. */
function paint(dot, p) {
  dot.style.background = p.dot_background;
  dot.style.borderColor = p.dot_border;
  dot.dataset.overdue = p.overdue ? '1' : '0';
  dot.classList.toggle('done', p.status === '완료');
  dot.classList.toggle('late', !!p.overdue);
  dot.classList.toggle('filtered', onlyOpen() && p.status === '완료');
}

/* ── 점이 들고 있는 것을 한 자리에서 갈아 끼운다 ──────────────────────
   **같은 모양으로 세 번 당했다.** 점은 옮겼는데 `onDates` 를 안 걸었고,
   걸었더니 색이 안 따라왔고, 그 다음엔 기간이 안 따라왔다 — 옮길 때
   복제한 점이 옛 `data-start`/`data-end`/`title` 을 그대로 물고 왔다.

   그래서 "점 하나가 무엇을 들고 있는가" 를 여기 한 자리에 모은다.
   새로 무언가를 실을 때 여기만 고치면 된다.

   `title` 은 **여기서 만들지 않는다.** 서버가 완성된 문장을 준다
   (`board.tooltip_of`). 화면이 조각을 다시 이어 붙이던 때는 조립하는 곳이
   둘이어서, 담당자를 바꿔도 점이 들고 있던 옛 이름이 계속 다시 쓰였다 —
   그 값을 갱신하는 사람이 아무도 없었기 때문이다. 색을 서버가 정하도록
   고친 것과 같은 자리다. */
function reload(dot, p) {
  paint(dot, p);
  // **기간도 따라온다.** 이것이 빠져서 옮긴 뒤 옛 기간이 비쳤다.
  // 다만 **서버가 날짜를 말해 줬을 때만** 손댄다 — 상태나 담당자를 바꾼
  // 응답에는 날짜가 없는데, 없는 것을 "비었다" 로 읽으면 멀쩡한 기간이
  // 지워져 비침이 사라진다.
  if ('start' in p) {
    if (p.start) { dot.dataset.start = p.start; dot.dataset.end = p.end || p.start; }
    else { delete dot.dataset.start; delete dot.dataset.end; }
  }
  if (p.tooltip !== undefined) dot.title = p.tooltip;
}

function applyStatus(runId, view) {
  dots(runId).forEach(dot => reload(dot, view));
}

/* 담당자는 점에 적히지 않지만 **툴팁에는 들어간다.** 서버가 새 문장을
   함께 돌려주므로 그것으로 갈아 끼운다. */
function applyAssignee(runId, _name, saved) {
  dots(runId).forEach(dot => reload(dot, saved));
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
  // **지우지 않고 치워 둔다.** 이 달 밖으로 내보낸 점을 지워 버리면, 패널을
  // 닫지 않은 채 다시 이 달 안으로 되돌렸을 때 찾을 것이 없어 돌아오지
  // 못한다 — 패널과 안내문이 서로 다른 날짜를 말하게 된다.
  // 숨긴 자리(`#calstash`)에 두면 `dots()` 가 계속 찾는다.
  existing.forEach(el => el.remove());
  reload(model, saved);

  const cell = document.querySelector(`.cal-cell[data-date="${iso}"]:not(.out)`);
  if (cell) {
    placeInGrid(cell, model);
    placeInWeekList(iso, model.cloneNode(true));
    // 되돌아왔으면 그 업무의 안내만 지운다. 다른 업무의 안내가 떠 있었다면
    // 건드리지 않는다 — 남의 말을 대신 지우면 그쪽이 조용해진다.
    if (note && note.dataset.run === String(runId)) say('');
  } else {
    stash(model);
    // **조용히 사라지면 "지워진 건가" 로 읽힌다.** 어디로 갔는지 말해 준다.
    const title = model.querySelector('.cal-t');
    // 조사는 붙여 쓴다 — "방명록 의" 가 아니라 "방명록의"
    say(`${title ? title.textContent.trim() + '의 ' : ''}마감일이 ${iso} 로 바뀌어 `
      + '이 달에는 보이지 않습니다. 그 달로 넘겨서 보세요.', runId);
  }
  recount();
}

/* 이 달 밖으로 나간 점을 치워 두는 자리. 화면에 그리지 않지만 DOM 에는
   남아 있어서, 되돌리면 그대로 살아난다. **숫자에는 들어가지 않는다** —
   `recount()` 가 이 자리를 빼고 세므로 `외 N건` 과 위쪽 건수가 화면과 맞는다. */
function stash(dot) {
  let box = document.getElementById('calstash');
  if (!box) {
    box = document.createElement('div');
    box.id = 'calstash';
    box.hidden = true;
    document.body.appendChild(box);
  }
  box.appendChild(dot);
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

  // **치워 둔 것(`#calstash`)은 세지 않는다.** 화면에 없는 것이 숫자에
  // 들어가면 `외 N건` 과 위쪽 건수가 눈에 보이는 것과 어긋난다.
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
  onAssignee: applyAssignee,
  isTaskClick: el => el.closest('.cal-dot'),
  // 점을 누르면 마우스가 움직이지 않아 `mouseout` 이 뜨지 않는다 —
  // 비침이 켜진 채로 패널이 열린다. 열릴 때 지운다.
  onOpen: clearSpan,

  /* ── 일부러 등록하지 않은 것 ──────────────────────────────────────
     빠뜨린 것과 구별되도록 여기 적는다. `call()` 은 없는 핸들러를 조용히
     건너뛰므로, 적어 두지 않으면 화면만 봐서는 둘을 가릴 수 없다.
     `tests/test_calendar.py` 가 이 목록과 실제 등록을 대조한다. */
  __unused: {
    goTo: '달력에는 스크롤해서 갈 자리가 없다. canGoTo:false 라 불리지도 않는다',
    link: '연결 강조는 보드의 바 사이에 선을 긋는 것이다. 점에는 그을 선이 없다',
    afterLayout: '다시 그릴 것이 없다. 달력은 서버가 그린 표 그대로다',
    onClose: '닫을 때 되돌릴 것이 없다. 보드는 연결 강조를 지우지만 달력엔 그을 선이 없고, 비침은 마우스를 떼면 사라진다',
    onDepartment: '담당팀을 옮기면 부서 색이 바뀌는데, 그건 통째로 다시 그리는 것이 맞다. 기본값(새로고침)을 쓴다',
    openFromUrl: '`?task=` 로 들어오면 그냥 열면 된다. 보드처럼 스크롤해서 옮길 자리가 없다',
  },
});

/* ── 점에 마우스를 올리면 그 업무의 기간이 비친다 (4-13) ──────────────
   **마감일에 점 하나** 는 그대로다. 기간을 늘 띠로 그리면 15일짜리 몇 개만
   있어도 달력이 꽉 차서 무엇이 급한지 안 보인다 — 그 판단은 유효하다.
   다만 마감일만 보면 "언제부터 하는 일인지" 를 알 수 없다. 한 번에 하나만
   뜨고 손을 떼면 사라지므로 위의 이유에 걸리지 않는다.

   **기간은 점이 이미 들고 있다**(`data-start`/`data-end`). 화면이 계산하거나
   서버에 다시 묻지 않는다.

   **좁은 화면에서는 하지 않는다.** 주 목록에는 날짜 격자가 없고 마우스도
   없다 — 탭으로 흉내 내면 점을 누르려다 띠가 뜬다. */
/* **폭이 두 곳에 있다.** CSS 는 `max-width:820px` 로 좁은 화면을 가르고
   여기는 `min-width:821px` 로 넓은 화면을 가른다. 미디어 쿼리를 CSS 에서
   읽어올 방법이 없으므로 값을 한 곳에 두지 못했다 —
   **한쪽을 바꾸면 다른 쪽도 같이 바꿔야 한다.** (retreat.css 의 820px) */
const 넓은화면 = () => matchMedia('(min-width: 821px)').matches;

function clearSpan() {
  document.querySelectorAll('.cal-cell.inspan').forEach(td => {
    td.classList.remove('inspan', 'span-head', 'span-tail');
  });
}

function showSpan(dot) {
  clearSpan();
  const from = dot.dataset.start, to = dot.dataset.end;
  if (!from || !to || !넓은화면()) return;

  // **격자에 보이는 칸까지 칠한다.** 점을 놓는 것은 이 달(`:not(.out)`)만이지만
  // 비침은 옆 달 칸도 포함한다 — 눈에 보이는 칸을 비워 두면 고장난 것처럼
  // 읽힌다. 이 차이는 CLAUDE.md 4-13 에 적어 두었다.
  const cells = [...document.querySelectorAll('.cal-grid .cal-cell[data-date]')]
    .filter(td => from <= td.dataset.date && td.dataset.date <= to);
  if (!cells.length) return;

  cells.forEach(td => td.classList.add('inspan'));
  // 기간이 이 달 안에서 시작·끝나면 그쪽 끝을 둥글게, 넘어가면 각지게 —
  // **잘렸다는 것이 모양으로 보인다.** 정확한 날짜는 점의 툴팁에 있다.
  if (cells[0].dataset.date === from) cells[0].classList.add('span-head');
  if (cells[cells.length - 1].dataset.date === to) {
    cells[cells.length - 1].classList.add('span-tail');
  }
}

/* `mouseover`/`mouseout` 을 문서에 하나만 건다 — 점이 `외 N건` 안에서
   나중에 펼쳐지거나 날짜가 바뀌어 다시 놓여도 그대로 동작한다. */
document.addEventListener('mouseover', e => {
  const dot = e.target.closest && e.target.closest('.cal-dot[data-start]');
  if (dot) showSpan(dot);
});
document.addEventListener('mouseout', e => {
  const dot = e.target.closest && e.target.closest('.cal-dot[data-start]');
  if (!dot) return;
  // 점 안에서 자식 요소끼리 옮겨 다니는 것은 떠난 것이 아니다
  if (e.relatedTarget && dot.contains(e.relatedTarget)) return;
  clearSpan();
});
// 화면 폭이 바뀌면 남아 있던 비침을 지운다.
// (패널이 열릴 때는 `Drawer.init` 의 `onOpen` 이 지운다 — 여기가 아니다)
addEventListener('resize', clearSpan);

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
