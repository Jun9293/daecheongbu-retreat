/* 수련회 준비 — 보드 — 시각 스펙 docs/mockups/retreat-board-v4.html
   서버가 그린 보드 위에서 필터 · 연결 강조 · 바 끌기를 담당한다.

   **상세 패널은 여기 없다.** `static/js/drawer.js` 한 벌을 보드와 달력이
   같이 쓴다 (CLAUDE.md 4-13). 여기서는 "패널이 무엇을 바꿨을 때 보드를
   어떻게 고쳐 그리는가" 만 알려 준다 — 아래 Drawer.init 이 그것이다. */
(function () {
'use strict';

const META = JSON.parse(document.getElementById('board-meta').textContent);

const board = document.getElementById('board');
const sheet = document.getElementById('sheet');
const wires = document.getElementById('wires');
const dw = document.getElementById('drawer');
const me = document.getElementById('me');
const opT = document.getElementById('opT');
const fchip = document.getElementById('fchip');

let curLink = null, dateSel = null;
/* 사용자가 직접 펴거나 접은 부서. 소속 기준 자동 접기보다 이 뜻이 우선한다 —
   상태를 바꿀 때마다 보고 있던 그룹이 닫히면 일을 할 수가 없다. */
const openedByHand = new Map();

const headers = () => [...sheet.querySelectorAll('.row.head .hc')];
const labelW = () => sheet.querySelector('.hlbl').offsetWidth;

/* ── D-1. 바 라벨: 바보다 길면 밖으로 흘러나간다 (CLAUDE.md 9장) ──
   바 위와 바 밖은 배경이 다르므로 같은 글자를 같은 자리에 한 겹 더 깔고
   바 경계에서 잘라 이어붙인다. 폭은 캔버스 measureText 로 잰다 —
   요소의 scrollWidth 는 '지연' 배지 유무에 따라 달라져 항목마다 결과가 갈린다. */
const gauge = document.createElement('canvas').getContext('2d');

function layoutLabels() {
  sheet.querySelectorAll('.bar').forEach(bar => {
    const txt = bar.querySelector('.txt');
    if (!txt) return;
    if (!bar.offsetParent) return;              // 접혀 있으면 폭을 잴 수 없다
    const cs = getComputedStyle(bar);
    gauge.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const label = txt.textContent;
    const need = gauge.measureText(label).width;
    const flag = bar.querySelector('.flag');
    const gap = parseFloat(cs.columnGap || cs.gap) || 0;
    const room = bar.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
      - (flag ? flag.offsetWidth + gap : 0);

    let spill = bar.querySelector('.txt.spill');
    if (need <= room + 0.5) {                   // 다 들어가면 겹칠 이유가 없다
      if (spill) spill.remove();
      txt.style.clipPath = '';
      delete bar.dataset.cut;
      return;
    }
    /* **밖으로 넘쳐도 되지만 같은 줄 다음 바 시작 − 6px 까지다** (목업 D).
       넘으면 `…` 로 끊고 **끊겼다고 적는다** — 끊긴 바는 팝업을 열어 제목
       전체를 보인다(4-1). 끊긴 줄 모르면 그 팝업이 안 열린다 */
    const 여유 = 다음바까지(bar) - 6;
    let 보일글 = label;
    if (need > 여유) {
      bar.dataset.cut = '1';
      // 글자 폭으로 자른다 — 글자 수로 세면 한글과 영문이 다르게 잘린다
      let lo = 0, hi = label.length;
      while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (gauge.measureText(label.slice(0, mid) + '…').width <= 여유) lo = mid;
        else hi = mid - 1;
      }
      보일글 = label.slice(0, lo) + '…';
    } else {
      delete bar.dataset.cut;
    }
    txt.style.clipPath = `inset(-4px ${Math.max(0, need - room)}px -4px -2px)`;
    if (!spill) {
      spill = document.createElement('span');
      spill.className = 'txt spill';
      spill.setAttribute('aria-hidden', 'true');
      txt.after(spill);
    }
    spill.textContent = 보일글;
    spill.style.left = txt.offsetLeft + 'px';
    spill.style.top = txt.offsetTop + 'px';
    spill.style.clipPath = `inset(-4px -8px -4px ${room}px)`;
  });
}

/* 같은 줄에서 이 바가 쓸 수 있는 폭 — **다음 바 시작까지** (목업 D).
   같은 `.lane` 안에서 세로로 겹치는(= 같은 줄에 놓인) 바만 본다: 접힌 Main
   아래에는 줄이 여럿이라 아래 줄의 바를 이웃으로 보면 애먼 데서 끊긴다 */
function 다음바까지(bar) {
  const lane = bar.parentElement;
  if (!lane) return 1e6;
  const 내왼쪽 = bar.offsetLeft, 내위 = bar.offsetTop;
  let 끝 = lane.clientWidth;
  lane.querySelectorAll('.bar').forEach(other => {
    if (other === bar || !other.offsetParent) return;
    if (Math.abs(other.offsetTop - 내위) > 2) return;   // 다른 줄이다
    if (other.offsetLeft <= 내왼쪽) return;
    끝 = Math.min(끝, other.offsetLeft);
  });
  return Math.max(0, 끝 - 내왼쪽);
}

/* ── 세로 격자선: 열마다 div 를 넣지 않고 한 번만 겹쳐 그린다 ── */
function drawGrid() {
  let box = sheet.querySelector('.gridlines');
  if (!box) {
    box = document.createElement('div');
    box.className = 'gridlines';
    sheet.insertBefore(box, sheet.firstChild);
  }
  box.innerHTML = headers().map(hc =>
    `<i class="${hc.classList.contains('shift') ? 'shift' : ''}" style="left:${hc.offsetLeft}px"></i>`
  ).join('');
}

/* ── 필터: 소속 · 미완료만 · 날짜 선택 ── */
function applyFilters() {
  const mine = me.value, onlyOpen = opT.checked, count = {};
  sheet.querySelectorAll('.row.main,.row.sub').forEach(row => {
    let ok = true;
    if (dateSel) {
      const a = row.dataset.s, b = row.dataset.e || row.dataset.s;
      if (b < dateSel[0] || a > dateSel[1]) ok = false;   // 기간이 선택 날짜와 겹치는지
    }
    if (onlyOpen && row.dataset.status === '완료') ok = false;
    row.dataset.ok = ok ? '1' : '';
    if (ok) count[row.dataset.of] = (count[row.dataset.of] || 0) + 1;
  });
  /* **접힌 줄에 눕는 바에도 건다** — 그 바들은 Main **행 안**이라 위의
     `.row` 훑기가 안 닿는다. 안 걸면 「미완료만」 을 켜도 완료된 하위 바가
     남고, 날짜 칸을 골라도 안 걸린 하위가 남는다(4-8 이 「그 안에서도 걸린
     업무만 펼쳐집니다」 라고 한 자리 · 커밋 전 검토가 잡았다).
     **META 에서 본다** — 눕는 바에는 날짜·상태가 안 실려 있다 */
  sheet.querySelectorAll('.bar.sl').forEach(bar => {
    const ids = (bar.dataset.runs || bar.dataset.run || '').split(' ').filter(Boolean);
    // 합친 바는 **하나라도 걸리면 남긴다** — 그 바 뒤에 업무가 여럿이라,
    // 하나가 안 걸린다고 지우면 걸린 업무가 화면에서 함께 사라진다
    const 남길까 = ids.some(id => {
      const m = META[id];
      if (!m) return true;                       // 모르면 안 지운다
      if (onlyOpen && m.status === '완료') return false;
      if (dateSel) {
        const a = m.start, b = m.end || m.start;
        if (!a || b < dateSel[0] || a > dateSel[1]) return false;
      }
      return true;
    });
    bar.hidden = !남길까;
  });
  sheet.querySelectorAll('.row.team').forEach(team => {
    const key = team.dataset.team, n = count[key] || 0;
    let open;
    if (dateSel) {                       // 날짜 선택 시: 해당 업무가 있는 부서만
      team.style.display = n ? '' : 'none';
      open = !!n;
      team.classList.toggle('collapsed', !open);
      team.classList.remove('dim');
    } else {
      team.style.display = '';
      const isMine = (mine === 'all' || key === mine || (mine === 'depts' && myKeys().includes(key)));
      open = openedByHand.has(key) ? openedByHand.get(key) : isMine;
      team.classList.toggle('collapsed', !open);
      // 소속 외 부서는 숨기지 않고 흐리게 — 존재는 인지되어야 한다
      team.classList.toggle('dim', !isMine && mine !== 'all');
    }
    // **글자가 아니라 마크업을 되돌린다** — `textContent` 로 되돌리면
    // 「· 지연 n건」 의 `<b class="lt">` 가 사라져 붉은 강조가 안 돌아온다
    const ct = team.querySelector('.ct');
    if (dateSel) ct.textContent = `${n}건`;
    else ct.innerHTML = team.dataset.ctHtml;
    sheet.querySelectorAll(`.row[data-of="${key}"]`).forEach(row => {
      row.style.display = (open && row.dataset.ok) ? '' : 'none';
    });
  });
  applyMobileFilters(mine, onlyOpen);
  layoutLabels();
  drawWires();
}

/* 모바일 목록은 D-주차로 묶여 있어 부서 접기가 없다.
   소속 외 업무는 숨기지 않고 흐리게 — 보드와 같은 원칙. */
function applyMobileFilters(mine, onlyOpen) {
  const list = document.getElementById('mlist');
  if (!list) return;
  let shown = 0;
  list.querySelectorAll('.mgroup').forEach(group => {
    let visible = 0;
    group.querySelectorAll('.mrow').forEach(row => {
      let ok = true;
      if (dateSel) {
        const a = row.dataset.s, b = row.dataset.e || row.dataset.s;
        if (b < dateSel[0] || a > dateSel[1]) ok = false;
      }
      if (onlyOpen && row.dataset.status === '완료') ok = false;
      row.style.display = ok ? '' : 'none';
      row.classList.toggle('dim', ok && mine !== 'all' && !(row.dataset.of === mine || (mine === 'depts' && myKeys().includes(row.dataset.of))));
      if (ok) visible++;
    });
    group.style.display = visible ? '' : 'none';
    group.querySelector('.n').textContent = `${visible}건`;
    shown += visible;
  });
  const empty = document.getElementById('mempty');
  if (empty) empty.hidden = shown > 0;
}

sheet.querySelectorAll('.row.team').forEach(team => {
  team.dataset.ctHtml = team.querySelector('.ct').innerHTML;
  team.querySelector('.lc').onclick = () => {
    team.classList.toggle('collapsed');
    const hidden = team.classList.contains('collapsed');
    openedByHand.set(team.dataset.team, !hidden);
    sheet.querySelectorAll(`.row[data-of="${team.dataset.team}"]`).forEach(row => {
      row.style.display = (!hidden && row.dataset.ok) ? '' : 'none';
    });
    layoutLabels();
    drawWires();
  };
});

/* 소속을 고르면 그 부서 제목이 스크롤 맨 위로 오게 한다.
   날짜 헤더가 sticky 로 위를 덮으므로 그 높이만큼 뺀다 — 안 빼면 제목이 가려진다. */
/* 마지막 부서를 골라도 제목이 맨 위로 올라오려면 그 아래에 스크롤할 것이 있어야 한다.
   시트 바깥(보드 안)에 딱 모자란 만큼만 여백을 만든다 — 격자선은 시트 안이라 번지지 않는다. */
let roomBelow = null;
function setRoomBelow(px) {
  if (!roomBelow) {
    roomBelow = document.createElement('div');
    roomBelow.className = 'room-below';
    roomBelow.setAttribute('aria-hidden', 'true');
    board.appendChild(roomBelow);
  }
  roomBelow.style.height = Math.max(0, Math.round(px)) + 'px';
}

/* 「내 부서」(depts) — 한 사람이 여러 부서에 속한다 (도막 4 · ④). 키 목록은
   드롭다운이 data-mykeys 로 들고 있다 — 서버가 준 것을 여기서 다시 세지 않는다 */
function myKeys() {
  const sel = document.querySelector('[data-deptpick]');
  return (sel && sel.dataset.mykeys) ? sel.dataset.mykeys.split(',').filter(Boolean) : [];
}

function scrollTeamToTop(key, smooth = true) {
  if (isMobile()) return;                 // 모바일은 D-주차 목록이라 부서 묶음이 없다
  const behavior = smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'smooth' : 'auto';
  if (key === 'all' || key === 'depts') { setRoomBelow(0); board.scrollTo({top: 0, behavior}); return; }
  const team = sheet.querySelector(`.row.team[data-team="${key}"]`);
  if (!team || !team.offsetParent) return;
  const head = sheet.querySelector('.row.head');
  const headH = head ? head.offsetHeight : 0;

  const below = sheet.getBoundingClientRect().bottom - team.getBoundingClientRect().top;
  setRoomBelow(board.clientHeight - headH - below);

  const br = board.getBoundingClientRect(), tr = team.getBoundingClientRect();
  board.scrollTo({top: Math.max(0, board.scrollTop + (tr.top - br.top) - headH), behavior});
}

me.onchange = () => { openedByHand.clear(); clearDate(); applyFilters(); scrollTeamToTop(me.value); };
opT.onchange = applyFilters;

function clearDate() {
  dateSel = null;
  sheet.querySelectorAll('.hc.sel').forEach(x => x.classList.remove('sel'));
  fchip.hidden = true;
}
sheet.querySelector('.row.head').addEventListener('click', e => {
  const hc = e.target.closest('.hc');
  if (!hc || !hc.dataset.cs) return;
  const same = dateSel && dateSel[0] === hc.dataset.cs && dateSel[1] === hc.dataset.ce;
  clearDate();
  if (!same) {
    dateSel = [hc.dataset.cs, hc.dataset.ce];
    hc.classList.add('sel');
    fchip.innerHTML = `<b>${hc.dataset.lb}</b> 포함 업무<span>×</span>`;
    fchip.hidden = false;
  }
  applyFilters();
});
fchip.onclick = () => { clearDate(); applyFilters(); };

/* ── 접힌 부서에 있어도 펼쳐서 보이게 ── */
function reveal(runId) {
  const m = META[runId];
  if (!m) return;
  const key = m.department_key || '__none__';
  const team = sheet.querySelector(`.row.team[data-team="${key}"]`);
  if (team) {
    team.style.display = '';
    team.classList.remove('collapsed', 'dim');
    openedByHand.set(key, true);
  }
  sheet.querySelectorAll(`.row[data-of="${key}"]`).forEach(row => {
    if (row.dataset.run === String(runId)) { row.dataset.ok = '1'; row.style.display = ''; }
    else if (row.dataset.ok) row.style.display = '';
  });
  /* **상위 Main 도 편다** (4-7). 2026-09-25 부터 하위가 있는 Main 이 기본
     접힘이라 **부서만 펴면 그 하위는 여전히 접힌 줄 안에 있다.** 접힌 하위
     줄은 `hidden` 이고 `[hidden]{display:none!important}` 가 이기므로
     `style.display=''` 로는 안 열린다 — 접기 고리를 그대로 부른다 */
  const 그줄 = sheet.querySelector(`.row.sub[data-run="${runId}"][data-parent]`);
  if (!그줄) return;
  let 위 = 그줄.previousElementSibling;
  while (위 && !위.classList.contains('main')) 위 = 위.previousElementSibling;
  if (위 && 위.classList.contains('folded')) 접거나편다(위, true);
}

function findBar(runId) {
  // **합친 바도 본다** — 접힌 Main 아래에서 여러 하위가 바 하나로 묶이면
  // 그 바가 그 run 들의 **유일한 산 자리**다(`data-runs`). 안 보면 연결선이
  // 숨은 바에서 출발해 아무 데도 안 그려진다 (4-5)
  const all = [...sheet.querySelectorAll(
    `.bar[data-run="${runId}"], .bar[data-runs~="${runId}"]`)];
  return all.find(x => !x.dataset.ghost && x.offsetParent) || all.find(x => x.offsetParent) || all[0];
}

/* ── 정렬 이동: 담당 부서를 먼저 펼치고, 한 칸 앞 날짜부터 보이게 ── */
function alignLeft(runId) {
  const m = META[runId];
  if (!m || !m.start) return;
  reveal(runId);
  const cells = headers();
  let index = cells.findIndex(hc => hc.dataset.cs <= m.start && m.start <= hc.dataset.ce);
  if (index < 0) index = cells.findIndex(hc => hc.dataset.ce >= m.start);
  if (index < 0) index = 0;
  const target = cells[Math.max(0, index - 1)];
  const left = Math.max(0, target.offsetLeft - labelW());

  let top = board.scrollTop;
  const el = findBar(runId);
  if (el && el.offsetParent) {
    const row = el.closest('.row');
    const br = board.getBoundingClientRect(), rr = row.getBoundingClientRect();
    top = Math.max(0, board.scrollTop + (rr.top - br.top) - Math.max(110, br.height / 2 - 70));
  }
  board.scrollTo({left, top, behavior: 'smooth'});   // 가로·세로를 한 번에
}

const isMobile = () => !board.offsetParent;   // 모바일에서는 보드가 숨겨진다

function goTo(runId) {
  if (isMobile()) { Drawer.open(runId); return; }
  const wasOpen = dw.classList.contains('open');
  reveal(runId); link(runId); Drawer.open(runId);
  if (wasOpen) alignLeft(runId);
  else setTimeout(() => alignLeft(runId), 250);
}

/* ── 연결 강조 ── */
function unlink() {
  curLink = null;
  wires.innerHTML = '';
  sheet.querySelectorAll('.lit,.anchor').forEach(e => e.classList.remove('lit', 'anchor'));
  sheet.querySelectorAll('.hl,.anchorrow').forEach(e => e.classList.remove('hl', 'anchorrow'));
}
function link(runId) {
  unlink();
  curLink = runId;
  const related = new Set((META[runId] || {}).related_run_ids || []);
  /* **합친 바도 본다** — 접힌 Main 아래의 하위는 그 바가 **유일한 산 자리**다
     (`data-runs`). 안 보면 `anchor` 가 숨은 바에만 붙어 `drawWires` 의
     `offsetParent` 걸러내기에서 전부 빠지고 **선이 통째로 안 그려진다** —
     4-5 가 「관련 업무가 하나도 없어도 선택 표시는 반드시 나타나야 한다」 고
     못박은 자리다(커밋 전 검토가 잡았다) */
  const 누구들 = el => el.dataset.run ? [Number(el.dataset.run)]
    : (el.dataset.runs || '').split(' ').filter(Boolean).map(Number);
  sheet.querySelectorAll('.bar[data-run], .bar[data-runs]').forEach(el => {
    const ids = 누구들(el), row = el.closest('.row');
    if (ids.includes(Number(runId))) { el.classList.add('anchor'); row.classList.add('anchorrow'); }
    else if (ids.some(id => related.has(id))) { el.classList.add('lit'); row.classList.add('hl'); }
  });
  drawWires();
}
function drawWires() {
  wires.innerHTML = '';
  if (!curLink) return;
  // 같은 업무가 관련팀에 고스트로 중복 존재하므로, 화면에 실제로 보이는 원본 바를 출발점으로
  const visible = [...sheet.querySelectorAll('.bar.anchor')].filter(e => e.offsetParent);
  const from = visible.find(e => !e.dataset.ghost) || visible[0];
  if (!from) return;
  const sr = sheet.getBoundingClientRect(), ar = from.getBoundingClientRect();
  const ax = ar.left - sr.left + ar.width / 2, ay = ar.top - sr.top + ar.height / 2;
  let d = '';
  sheet.querySelectorAll('.bar.lit').forEach(to => {
    if (!to.offsetParent) return;
    const lr = to.getBoundingClientRect();
    const lx = lr.left - sr.left + lr.width / 2, ly = lr.top - sr.top + lr.height / 2;
    const mx = (ax + lx) / 2;
    d += `<path d="M ${ax} ${ay} C ${mx} ${ay}, ${mx} ${ly}, ${lx} ${ly}"/>`;
    d += `<circle cx="${lx}" cy="${ly}" r="2.6"/>`;
  });
  if (d) d += `<circle cx="${ax}" cy="${ay}" r="4.5"/>`;
  wires.innerHTML = d;
  wires.setAttribute('width', sheet.scrollWidth);
  wires.setAttribute('height', sheet.scrollHeight);
}
addEventListener('resize', () => { drawGrid(); layoutLabels(); drawWires(); });

/* ── 바를 끌어 날짜 옮기기 ────────────────────────────────────────────
   가로로만 움직인다. 위아래로 옮기면 담당 부서가 바뀌는 셈인데, 그건 날짜를
   고치는 일과 전혀 다른 결정이므로 드래그로 일어나서는 안 된다.
   칸에 물려 떨어진다 — 주 단위 구간에서는 그 주로, 일 단위 구간에서는 그 날로. */
const DAY_MS = 864e5;
const isoOf = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const dateOf = iso => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); };

/* 커서가 놓인 칸 → 새 시작일. 주 단위 칸이면 원래 요일을 지켜 그 주 안에 놓는다. */
function startForCell(hc, weekday) {
  const from = dateOf(hc.dataset.cs);
  if (hc.dataset.cs === hc.dataset.ce) return from;          // 하루짜리 칸
  const span = Math.round((dateOf(hc.dataset.ce) - from) / DAY_MS);
  return new Date(from.getTime() + Math.min(weekday, span) * DAY_MS);
}

/* 끌어 놓을 칸은 '가장 가까운' 칸이다.
   바의 왼쪽 끝이 들어간 칸으로 정하면, 시작할 때 이미 경계에 붙어 있어서
   왼쪽으로 1px 만 움직여도 앞 칸으로 넘어간다. 오른쪽은 한 칸 폭을 다 가야 하고.
   칸 왼쪽 모서리와의 거리로 고르면 양쪽 모두 반 칸을 움직여야 넘어간다. */
function nearestCell(left) {
  const cells = headers();
  let best = cells[0], bestGap = Infinity;
  for (const hc of cells) {
    const gap = Math.abs(hc.offsetLeft - left);
    if (gap < bestGap) { bestGap = gap; best = hc; }
  }
  return best;
}

function canDrag(bar) {
  const m = META[bar.dataset.run];
  return !!m && !bar.dataset.ghost && m.can_edit !== false;
}

sheet.addEventListener('mousedown', e => {
  if (e.button !== 0) return;
  const bar = e.target.closest('.bar[data-run]');
  if (!bar || !canDrag(bar)) return;

  const runId = bar.dataset.run, meta = META[runId];
  if (!meta || !meta.start) return;
  const origStart = dateOf(meta.start);
  const spanDays = Math.round((dateOf(meta.end || meta.start) - origStart) / DAY_MS);
  const weekday = origStart.getDay();
  const grabX = e.clientX;
  const startCol = Number(bar.style.gridColumn.split('/')[0]);
  const width = Number(bar.style.gridColumn.split('/')[1]) - startCol;

  let moved = false, target = null;
  e.preventDefault();
  bar.classList.add('dragging');
  document.body.classList.add('dragging-bar');

  const move = ev => {
    if (!moved && Math.abs(ev.clientX - grabX) < 3) return;
    moved = true;
    // 원래 칸의 왼쪽 모서리에서 끈 거리만큼 옮긴 자리 — 매번 원점에서 다시 잰다
    const cells = headers();
    const origin = cells[Math.min(startCol, cells.length) - 1];
    const hc = nearestCell(origin.offsetLeft + (ev.clientX - grabX));
    if (!hc) return;
    const next = startForCell(hc, weekday);
    if (target && isoOf(target) === isoOf(next)) return;
    target = next;
    const col = headers().indexOf(hc) + 1;
    bar.style.gridColumn = `${col}/${col + width}`;   // 미리 보여준다 (행은 그대로)
    showGhostDate(bar, next, spanDays);
  };

  const up = async () => {
    removeEventListener('mousemove', move);
    removeEventListener('mouseup', up);
    bar.classList.remove('dragging');
    document.body.classList.remove('dragging-bar');
    hideGhostDate();
    if (!moved || !target) { bar.style.gridColumn = `${startCol}/${startCol + width}`; return; }
    Drawer.noteDrag();                          // 드래그 끝의 클릭을 무시시킨다

    const start = isoOf(target);
    const end = isoOf(new Date(target.getTime() + spanDays * DAY_MS));
    if (start === meta.start) { bar.style.gridColumn = `${startCol}/${startCol + width}`; return; }

    const res = await fetch(`/board/task/${runId}/dates`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({start, end}),
    });
    if (!res.ok) {
      alert((await res.json().catch(() => ({}))).detail || '날짜를 바꾸지 못했습니다.');
      bar.style.gridColumn = `${startCol}/${startCol + width}`;
      return;
    }
    const saved = await res.json();
    applySavedDates(runId, saved);
    Drawer.applyDates(runId, saved);
  };

  addEventListener('mousemove', move);
  addEventListener('mouseup', up);
});

/* 끌고 있는 동안 바뀔 날짜를 붙여 보여준다 */
let ghostDate = null;
function showGhostDate(bar, start, spanDays) {
  if (!ghostDate) {
    ghostDate = document.createElement('div');
    ghostDate.className = 'dragdate mono';
    document.body.appendChild(ghostDate);
  }
  const end = new Date(start.getTime() + spanDays * DAY_MS);
  const fmt = d => `${d.getMonth() + 1}/${d.getDate()}`;
  ghostDate.textContent = spanDays ? `${fmt(start)} – ${fmt(end)}` : fmt(start);
  const r = bar.getBoundingClientRect();
  ghostDate.style.left = Math.round(r.left) + 'px';
  ghostDate.style.top = Math.round(r.top - 26) + 'px';
}
function hideGhostDate() { if (ghostDate) { ghostDate.remove(); ghostDate = null; } }

/* 담당자를 보드와 모바일 목록에 반영한다 */
function applyAssignee(runId, name) {
  if (META[runId]) META[runId].assignee = name;
  sheet.querySelectorAll(`.row[data-run="${runId}"] .who`).forEach(el => {
    el.textContent = name || '';
    el.hidden = !name;
  });
  document.querySelectorAll(`.mrow[data-run="${runId}"] .who`).forEach(el => {
    el.textContent = name || '';
    el.hidden = !name;
  });
}

/* 저장된 날짜를 화면 곳곳에 반영한다 */
function applySavedDates(runId, saved) {
  META[runId].start = saved.start;
  META[runId].end = saved.end;
  META[runId].d_week = saved.d_week;
  sheet.querySelectorAll(`.row[data-run="${runId}"]`).forEach(row => {
    row.dataset.s = saved.start;
    row.dataset.e = saved.end;
  });
  // 축보다 앞으로 나간 업무는 그릴 칸이 없다. 보드를 다시 그려 축을 늘린다.
  const cells = headers();
  if (saved.start < cells[0].dataset.cs) { location.reload(); return; }

  // 고스트 바까지 같은 자리로 옮긴다.
  // 범위 밖은 가까운 쪽 끝에 붙인다 — 앞은 첫 칸, 뒤는 마지막 칸.
  // (못 찾았다고 무조건 마지막 칸으로 보내면 앞으로 당길수록 뒤로 밀린다)
  const colOf = iso => {
    const i = cells.findIndex(hc => hc.dataset.cs <= iso && iso <= hc.dataset.ce);
    if (i >= 0) return i + 1;
    return iso < cells[0].dataset.cs ? 1 : cells.length;
  };
  const a = colOf(saved.start), b = Math.max(a, colOf(saved.end));
  sheet.querySelectorAll(`.bar[data-run="${runId}"]`).forEach(el => {
    el.style.gridColumn = `${a}/${b + 1}`;
    // **색도 서버가 준 것을 그대로 쓴다.** `/dates` 는 `/status` 와 같은 모양으로
    // 생김새를 돌려준다(`board.paint_of`) — 한쪽만 고치면 또 두 벌이 된다.
    // 보드의 바는 저장된 상태로 칠하므로 날짜만 옮기면 지금은 값이 같지만,
    // 규칙이 바뀌면 여기가 따라오지 않는 것이 바로 어긋나는 자리다.
    if (saved.bar_background && !el.dataset.ghost) {
      el.style.background = saved.bar_background;
      el.style.borderColor = saved.bar_border;
    }
  });
  if (saved.bar_border) {
    document.querySelectorAll(`.mrow[data-run="${runId}"] .st`).forEach(el => {
      el.style.background = saved.bar_border;
    });
  }
  document.querySelectorAll(`.mrow[data-run="${runId}"]`).forEach(row => {
    row.dataset.s = saved.start;
    row.dataset.e = saved.end;
    const meta = row.querySelector('.meta span:last-child');
    if (meta) meta.textContent = saved.label;
  });
  layoutLabels();
  drawWires();
}

/* 패널에서 상태를 바꾸면 보드의 바도 따라 바뀐다 — 다시 불러오지 않는다.

   상태는 `view.status` 가 들고 온다 (`board.paint_of`). 인자로 또 받으면
   같은 값이 두 자리에 있게 되고, 둘이 어긋났을 때 어느 쪽이 맞는지 알 수 없다. */
function applyStatus(runId, view) {
  // 보이는 상태는 배지에서 온다 (board.paint_of · 4-3) — 기한이 지났으면
  // '지연'. view.status 는 저장값이라 '지연' 을 들지 않는다.
  const status = (view.badge && view.badge.label) || view.status;
  META[runId].status = status;
  sheet.querySelectorAll(`.bar[data-run="${runId}"]`).forEach(el => {
    el.closest('.row').dataset.status = status;
    if (el.dataset.ghost) return;
    el.classList.remove('대기', '진행중', '완료', '지연');
    el.classList.add(status);
    el.style.background = view.bar_background;
    el.style.borderColor = view.bar_border;
    const flag = el.querySelector('.flag');
    if (flag) flag.remove();
    if (status === '지연') el.insertAdjacentHTML('afterbegin', '<span class="flag">지연</span>');
  });
  document.querySelectorAll(`.mrow[data-run="${runId}"]`).forEach(row => {
    row.dataset.status = status;
    row.classList.toggle('done', status === '완료');
    row.querySelector('.st').style.background = view.bar_border;
    const f = row.querySelector('.flag');
    if (f) f.remove();
    if (status === '지연') row.insertAdjacentHTML('beforeend', '<span class="flag">지연</span>');
  });
  applyFilters();
}

/* ── 보드 클릭 ── */
/* **안 여는 자리** — 접기 손잡이와 「하위 n건」. 둘 다 `.lc[data-go]` 안에
   있어서 그냥 두면 **행을 여는 쪽이 먼저 돈다**(같은 요소에 걸린 리스너는
   등록 순서대로 불리므로 `stopPropagation` 으로는 못 막는다). 「여는 자리」
   목록을 두지 않고 **안 여는 자리**만 적는 것은 4-14 가 정한 그 방식이다 */
const 보드안여는곳 = '.fold, .subn';

sheet.addEventListener('click', e => {
  if (Drawer.recentDrag()) return;
  if (e.target.closest(보드안여는곳)) return;
  const go = e.target.closest('[data-go]');
  if (go) { goTo(go.dataset.go); return; }
  const bar = e.target.closest('.bar[data-run]');
  if (bar) { link(bar.dataset.run); Drawer.open(bar.dataset.run); }
});
sheet.addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const bar = e.target.closest('.bar[data-run]');
  if (bar) { e.preventDefault(); link(bar.dataset.run); Drawer.open(bar.dataset.run); }
});

const mlist = document.getElementById('mlist');
if (mlist) mlist.addEventListener('click', e => {
  const row = e.target.closest('.mrow');
  if (row) Drawer.open(row.dataset.run);
});

/* ── 상세 패널에게 "보드는 이렇게 고쳐 그린다" 를 알려 준다 ──────────
   패널 자체(화면과 코드)는 달력과 함께 쓰는 한 벌이다 (CLAUDE.md 4-13). */
Drawer.init({
  canGoTo: true,
  meta: runId => META[runId] || null,
  onClose: unlink,
  afterLayout: drawWires,
  link,
  goTo: id => {
    goTo(id);
    setTimeout(() => {
      const el = findBar(id);
      if (el) el.animate([{opacity: 1}, {opacity: .35}, {opacity: 1}], {duration: 520, iterations: 2});
    }, 300);
  },
  onStatus: applyStatus,
  onDates: applySavedDates,
  onAssignee: applyAssignee,
  /* 제목이 바뀌면 바의 라벨과 왼쪽 목록이 따라간다 — 라벨은 넘침을 다시
     재야 한다(spill). 번호(runno)는 그대로다 (4-14). */
  onTitle(runId, title) {
    if (META[runId]) META[runId].title = title;
    sheet.querySelectorAll(`.bar[data-run="${runId}"] .txt:not(.spill)`).forEach(t => {
      t.textContent = (t.textContent.startsWith('↳ ') ? '↳ ' : '') + title;
    });
    sheet.querySelectorAll(`.row[data-run="${runId}"] .lc .nm`).forEach(nm => {
      const no = nm.querySelector('.runno');
      const ghost = nm.textContent.trimStart().startsWith('↳');
      nm.textContent = (ghost ? '↳ ' : '') + title;
      if (no) nm.prepend(no);
    });
    document.querySelectorAll(`.mrow[data-run="${runId}"] .nm`).forEach(nm => {
      nm.textContent = title;
    });
    layoutLabels();
  },
  isTaskClick: el => el.closest('.bar[data-run],[data-go]'),
  // 알림·달력에서 `?task=` 로 들어오면 그 자리로 옮기고 연다
  openFromUrl: run => {
    goTo(run);
    setTimeout(() => { Drawer.open(run); link(run); }, 320);
  },

  /* ── 일부러 등록하지 않은 것 ────────────────────────────────────────
     빠뜨린 것과 구별되도록 여기 적는다. `call()` 은 없는 핸들러를 조용히
     건너뛰므로, 적어 두지 않으면 화면만 봐서는 둘을 가릴 수 없다.
     `tests/test_calendar.py` 가 이 목록과 실제 등록을 대조한다. */
  /* **훅 계약의 도장** (`__unusedFor`). `drawer.js` 의 머리말과 `call()` 이름
     목록만 해시로 뜬 값이다 — 파일 전체가 아니다. 무관한 수정에 걸리면 사람이
     읽지 않고 도장만 찍게 된다.

     낡음은 아무 때나 생기지 않는다. **계약이 바뀌는 순간**에 생긴다 — 두 번의
     사고가 둘 다 `drawer.js` 가 새 일을 시작한 그 커밋에서 났다(`onOpen`·
     `onAssignee`). 그래서 계약이 바뀌면 여기가 안 맞아 빨개지고, 그때 아래
     목록을 처음부터 다시 읽는다. 3단계의 정적 주소 해시와 같은 수법이다 —
     **내용이 바뀌면 이름도 바뀌게 해서, 옛것을 조용히 쓰지 못하게 한다.** */
  __unusedFor: 'af295bbc',
  __unused: {
    onOpen: '패널이 열릴 때는 할 일이 없다. 연결선은 afterLayout 이 240ms 뒤에 다시 그린다',
    onDepartment: '담당팀을 옮기면 업무가 다른 부서의 줄로 통째로 간다 (4-9). '
      + '행 구조가 바뀌는 것이라 부분 수정보다 다시 그리는 것이 맞다 — 기본값(새로고침)을 쓴다',
    onRelatedTeams: '관련팀이 바뀌면 고스트 바가 다른 부서 줄에 생기고 없어진다 — '
      + '행 구조가 바뀌는 것이라 담당팀 이동과 같이 기본값(새로고침)을 쓴다',
  },
});

/* ── 3단계: 접힘 · 오늘 · 업무 팝업 (목업 D · F) ──────────────────── */

/* **펼침 상태는 기기에 남는다** (4-1). 서버는 늘 접힌 채로 내고, 여기서
   남은 값만 펼친다 — 서버가 남은 값을 모르므로 펼친 채로 내면 접어 둔
   사람의 화면이 한 번 깜빡인다. 회차마다 따로 남긴다 */
const FOLDKEY = 'dcb.board.open.' + (sheet.dataset.retreat || '0');
const 펼친것 = () => {
  try { return new Set(JSON.parse(localStorage.getItem(FOLDKEY) || '[]')); }
  catch { return new Set(); }        // 사파리 비공개 창 등 — 없는 것으로 본다
};
const 펼침을남긴다 = set => {
  try { localStorage.setItem(FOLDKEY, JSON.stringify([...set])); } catch {}
};

function 접거나편다(row, open) {
  row.classList.toggle('folded', !open);
  const btn = row.querySelector('.fold');
  if (btn) {
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    const 말 = open ? '하위 업무 접기' : '하위 업무 펼치기';
    // 보이는 말과 읽어 주는 이름은 같은 글자여야 한다 (4-0 의 그 규칙)
    btn.title = 말; btn.setAttribute('aria-label', 말);
    btn.textContent = open ? '▼' : '▶';
  }
  // 하위 줄은 Main 바로 다음부터 이어져 있다
  let next = row.nextElementSibling;
  while (next && next.classList.contains('sub') && next.dataset.parent) {
    next.hidden = !open;
    next = next.nextElementSibling;
  }
}

(function 접힘을세운다() {
  const 열린 = 펼친것();
  sheet.querySelectorAll('.row.main[data-subs]').forEach(row => {
    접거나편다(row, 열린.has(row.dataset.run));
  });
})();

sheet.addEventListener('click', e => {
  const 손잡이 = e.target.closest('.fold, .subn');
  if (!손잡이) return;
  e.stopPropagation();                       // 행을 여는 것과 겹치지 않게
  const row = 손잡이.closest('.row.main[data-subs]');
  if (!row) return;
  const open = row.classList.contains('folded');
  접거나편다(row, open);
  const 열린 = 펼친것();
  open ? 열린.add(row.dataset.run) : 열린.delete(row.dataset.run);
  펼침을남긴다(열린);
  // 줄이 늘고 줄었다 — 격자선과 연결선을 다시 잰다
  drawGrid(); layoutLabels(); drawWires();
});

/* ── 오늘 ── */
const todayLine = sheet.querySelector('.todayline');
const todayCol = Number(getComputedStyle(sheet).getPropertyValue('--todaycol')) || 0;
function 오늘선을놓는다() {
  if (!todayLine || !todayCol) return;
  const hc = headers()[todayCol - 1];
  if (!hc) return;
  sheet.style.setProperty('--todayx', (hc.offsetLeft + hc.offsetWidth / 2) + 'px');
}
/* 수련회 띠 — 머리 칸을 재서 본문까지 같은 자리에 깐다 (목업 D).
   칸 폭이 구간마다 달라 CSS 로는 못 더한다(오늘 선과 같은 자리) */
const 수련회띠 = sheet.querySelector('.retreatband');
function 수련회띠를놓는다() {
  if (!수련회띠) return;
  const rt = sheet.querySelector('.row.head .hc.rt');
  if (!rt) return;
  sheet.style.setProperty('--rtx', rt.offsetLeft + 'px');
  sheet.style.setProperty('--rtw', rt.offsetWidth + 'px');
}
오늘선을놓는다();
수련회띠를놓는다();
addEventListener('resize', () => { 오늘선을놓는다(); 수련회띠를놓는다(); });

const todayBtn = document.getElementById('todaybtn');
if (todayBtn) todayBtn.onclick = () => {
  const hc = headers()[todayCol - 1];
  if (!hc) return;
  // 오늘 선이 **가운데** 오게 (목업 D). 왼쪽 고정 칸만큼은 늘 가려져 있다
  const 가림 = sheet.querySelector('.hlbl').offsetWidth;
  board.scrollTo({
    left: Math.max(0, hc.offsetLeft - 가림 - (board.clientWidth - 가림) / 2 + hc.offsetWidth / 2),
    behavior: 'smooth',
  });
};

/* ── 업무 팝업 (F) ────────────────────────────────────────────────────
   여는 조건은 셋이다 (4-1) — **끊긴 바 · 합친 바 · 축 상한 밖 바**.
   마지막 것은 **제목이 안 끊겨도** 연다: 바는 마지막 칸에 붙고 `→` 만
   달리므로, 팝업이 안 열리면 그 업무의 실제 날짜를 말할 자리가 화면
   어디에도 없다. 왼쪽 칸에서 `…` 로 끊긴 이름도 같은 팝업이다. */
function 팝업감(el) {
  if (!el) return null;
  if (el.classList.contains('bar')) {
    const 끊김 = el.dataset.cut, 합침 = el.classList.contains('merged');
    const 축밖 = !!el.querySelector('.beyond');
    if (!끊김 && !합침 && !축밖) return null;
    return 실은것(el);
  }
  // 왼쪽 칸의 이름 — `…` 로 끊겼을 때만
  const nm = el.closest('.lc') && el.closest('.lc').querySelector('.nm');
  if (!nm || nm.scrollWidth <= nm.clientWidth + 1) return null;
  const row = el.closest('.row[data-run]');
  // 왼쪽 칸도 **그 줄의 바가 실어 온 것**을 쓴다 — 여기서 새로 짓지 않는다
  return row ? 실은것(row.querySelector('.bar[data-pop]')) : null;
}

/* **문장을 만드는 곳은 `board.popup_meta` 하나다**(4-1). 화면은 서버가
   실어 보낸 것을 읽기만 한다.

   전에는 여기 둘째 벌(`메타줄`)이 있었고 주석에 「서버가 준 한 줄이 없을
   때만 쓰는 되돌림」 이라고 적어 두었는데, **`data-pop` 을 다는 곳이 합친
   바뿐이라 끊긴 바는 실제로 그쪽을 타고 있었다** — 되돌림이 아니라 주
   경로였다(커밋 전 검토). 둘이 같은 글자를 내고 있어서 눈에 안 띄었다.
   이제 보통 바도 `data-pop` 을 달고, 짓는 코드는 화면에 없다. */
function 실은것(el) {
  if (!el || !el.dataset.pop) return null;
  try { return JSON.parse(el.dataset.pop); } catch { return null; }
}

sheet.addEventListener('mouseover', e => {
  const el = e.target.closest('.bar, .lc .nm');
  const items = 팝업감(el);
  if (items) window.TaskPop && window.TaskPop.open(el.closest('.bar') || el, items);
});
sheet.addEventListener('mouseout', e => {
  if (e.target.closest('.bar, .lc .nm')) window.TaskPop && window.TaskPop.later();
});
/* 휴대폰 — **첫 탭이 팝업이고 두 번째 탭이 드로어다** (4-1 · 목업 F).
   손가락에는 호버가 없어 위의 `mouseover` 가 안 온다.

   **둘째 탭을 흘려 보내야 한다.** 전에는 여기서 늘 `stopPropagation()` 을
   걸어 **드로어를 여는 버블 리스너가 영영 안 돌았다** — 몇 번을 탭해도
   팝업만 다시 떴다(커밋 전 검토). 팝업이 `pointerdown` 에서 이미 닫히므로
   「지금 떠 있나」 로는 못 가른다: **누가 띄웠는지**를 따로 기억한다.

   820px 아래에서는 보드가 숨지만 **`hover:none` 인 터치 노트북**은 그
   폭에서도 보드를 본다(4-0 이 짚어 둔 그 기기다). */
let 팝업띄운바 = null;
sheet.addEventListener('click', e => {
  if (matchMedia('(hover:hover)').matches) return;
  if (e.target.closest(보드안여는곳)) return;
  const el = e.target.closest('.bar, .lc .nm');
  const 대상 = el && (el.closest('.bar') || el);
  if (!대상) { 팝업띄운바 = null; return; }
  if (팝업띄운바 === 대상) {           // 두 번째 탭 — 그대로 흘려 보낸다
    팝업띄운바 = null;
    window.TaskPop && window.TaskPop.close();
    return;
  }
  const items = 팝업감(el);
  if (!items) { 팝업띄운바 = null; return; }
  e.preventDefault(); e.stopPropagation();
  팝업띄운바 = 대상;
  window.TaskPop && window.TaskPop.open(대상, items);
}, true);

drawGrid();
applyFilters();
// 글꼴이 로드되기 전에 재면 폭이 틀리므로 다시 계산한다
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { drawGrid(); layoutLabels(); drawWires(); });
}
})();
