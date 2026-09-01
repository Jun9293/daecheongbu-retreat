/* 준비 단계 보드 — 시각 스펙 docs/mockups/retreat-board-v4.html
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
      return;
    }
    txt.style.clipPath = `inset(-4px ${Math.max(0, need - room)}px -4px -2px)`;
    if (!spill) {
      spill = document.createElement('span');
      spill.className = 'txt spill';
      spill.setAttribute('aria-hidden', 'true');
      txt.after(spill);
    }
    spill.textContent = label;
    spill.style.left = txt.offsetLeft + 'px';
    spill.style.top = txt.offsetTop + 'px';
    spill.style.clipPath = `inset(-4px -8px -4px ${room}px)`;
  });
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
      const isMine = (mine === 'all' || key === mine);
      open = openedByHand.has(key) ? openedByHand.get(key) : isMine;
      team.classList.toggle('collapsed', !open);
      // 소속 외 부서는 숨기지 않고 흐리게 — 존재는 인지되어야 한다
      team.classList.toggle('dim', !isMine && mine !== 'all');
    }
    team.querySelector('.ct').textContent = dateSel ? `${n}건` : team.dataset.ct;
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
      row.classList.toggle('dim', ok && mine !== 'all' && row.dataset.of !== mine);
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
  team.dataset.ct = team.querySelector('.ct').textContent;
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

function scrollTeamToTop(key, smooth = true) {
  if (isMobile()) return;                 // 모바일은 D-주차 목록이라 부서 묶음이 없다
  const behavior = smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'smooth' : 'auto';
  if (key === 'all') { setRoomBelow(0); board.scrollTo({top: 0, behavior}); return; }
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
}

function findBar(runId) {
  const all = [...sheet.querySelectorAll(`.bar[data-run="${runId}"]`)];
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
  sheet.querySelectorAll('.bar[data-run]').forEach(el => {
    const id = Number(el.dataset.run), row = el.closest('.row');
    if (id === Number(runId)) { el.classList.add('anchor'); row.classList.add('anchorrow'); }
    else if (related.has(id)) { el.classList.add('lit'); row.classList.add('hl'); }
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
  });
  document.querySelectorAll(`.mrow[data-run="${runId}"]`).forEach(row => {
    row.dataset.s = saved.start;
    row.dataset.e = saved.end;
    const meta = row.querySelector('.meta span:last-child');
    if (meta) meta.textContent = saved.label;
  });
  layoutLabels();
  drawWires();
}

/* 패널에서 상태를 바꾸면 보드의 바도 따라 바뀐다 — 다시 불러오지 않는다 */
function applyStatus(runId, status, view) {
  META[runId].status = status;
  sheet.querySelectorAll(`.bar[data-run="${runId}"]`).forEach(el => {
    el.closest('.row').dataset.status = status;
    if (el.dataset.ghost) return;
    el.classList.remove('대기', '진행중', '완료', '지연');
    el.classList.add(status);
    el.style.background = view.background;
    el.style.borderColor = view.border;
    const flag = el.querySelector('.flag');
    if (flag) flag.remove();
    if (status === '지연') el.insertAdjacentHTML('afterbegin', '<span class="flag">지연</span>');
  });
  document.querySelectorAll(`.mrow[data-run="${runId}"]`).forEach(row => {
    row.dataset.status = status;
    row.classList.toggle('done', status === '완료');
    row.querySelector('.st').style.background = view.border;
    const f = row.querySelector('.flag');
    if (f) f.remove();
    if (status === '지연') row.insertAdjacentHTML('beforeend', '<span class="flag">지연</span>');
  });
  applyFilters();
}

/* ── 보드 클릭 ── */
sheet.addEventListener('click', e => {
  if (Drawer.recentDrag()) return;
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
  isTaskClick: el => el.closest('.bar[data-run],[data-go]'),
  // 알림·달력에서 `?task=` 로 들어오면 그 자리로 옮기고 연다
  openFromUrl: run => {
    goTo(run);
    setTimeout(() => { Drawer.open(run); link(run); }, 320);
  },
});

drawGrid();
applyFilters();
// 글꼴이 로드되기 전에 재면 폭이 틀리므로 다시 계산한다
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { drawGrid(); layoutLabels(); drawWires(); });
}
})();
