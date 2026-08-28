/* 준비 단계 보드 — 시각 스펙 docs/mockups/retreat-board-v4.html
   서버가 그린 보드 위에서 필터 · 연결 강조 · 상세 패널을 담당한다. */
(function () {
'use strict';

const META = JSON.parse(document.getElementById('board-meta').textContent);
const STATUS = {
  '대기':   {label: '예정',   color: '#4A544F'},
  '진행중': {label: '진행중', color: '#1668E3'},
  '완료':   {label: '완료',   color: '#8B948F'},
  '지연':   {label: '지연',   color: '#C8442E'},
};
const WD = ['일', '월', '화', '수', '목', '금', '토'];

const board = document.getElementById('board');
const sheet = document.getElementById('sheet');
const wires = document.getElementById('wires');
const dw = document.getElementById('drawer');
const me = document.getElementById('me');
const opT = document.getElementById('opT');
const fchip = document.getElementById('fchip');

let cur = null, curLink = null, dateSel = null, dragEnd = 0, detail = null;

const headers = () => [...sheet.querySelectorAll('.row.head .hc')];
const labelW = () => sheet.querySelector('.hlbl').offsetWidth;
const md = iso => iso ? iso.slice(5).replace('-', '/') : '';

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
      team.classList.toggle('collapsed', !isMine);
      // 소속 외 부서는 숨기지 않고 흐리게 — 존재는 인지되어야 한다
      team.classList.toggle('dim', !isMine && mine !== 'all');
      open = isMine;
    }
    team.querySelector('.ct').textContent = dateSel ? `${n}건` : team.dataset.ct;
    sheet.querySelectorAll(`.row[data-of="${key}"]`).forEach(row => {
      row.style.display = (open && row.dataset.ok) ? '' : 'none';
    });
  });
  drawWires();
}

sheet.querySelectorAll('.row.team').forEach(team => {
  team.dataset.ct = team.querySelector('.ct').textContent;
  team.querySelector('.lc').onclick = () => {
    team.classList.toggle('collapsed');
    const hidden = team.classList.contains('collapsed');
    sheet.querySelectorAll(`.row[data-of="${team.dataset.team}"]`).forEach(row => {
      row.style.display = (!hidden && row.dataset.ok) ? '' : 'none';
    });
    drawWires();
  };
});

me.onchange = () => { clearDate(); applyFilters(); };
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

function goTo(runId) {
  const wasOpen = dw.classList.contains('open');
  reveal(runId); link(runId); openDrawer(runId);
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
addEventListener('resize', () => { drawGrid(); drawWires(); });

/* ── 상세 패널 ── */
async function openDrawer(runId) {
  cur = runId;
  const m = META[runId] || {};
  document.getElementById('dtitle').textContent = m.title || '';
  document.getElementById('dlog').innerHTML = '<div class="empty">불러오는 중…</div>';
  dw.classList.add('open');
  dw.setAttribute('aria-hidden', 'false');
  document.body.classList.add('dopen');
  setTimeout(drawWires, 240);

  const res = await fetch(`/board/task/${runId}`, {headers: {'Accept': 'application/json'}});
  if (!res.ok) { document.getElementById('dlog').innerHTML = '<div class="empty">불러오지 못했습니다.</div>'; return; }
  detail = await res.json();
  if (String(cur) !== String(runId)) return;
  renderDrawer();
}

function renderDrawer() {
  const d = detail;
  const st = STATUS[d.status] || STATUS['대기'];
  document.getElementById('dkick').innerHTML =
    `<span class="chip solid" style="background:${d.department_color}">${d.department}</span>
     <span class="chip">${d.kind_label}</span>
     <button class="chip stat" id="statchip" ${d.can_edit ? '' : 'disabled'}>
       <span class="cv" style="background:${st.color}"></span>${st.label}${d.can_edit ? ' ▾' : ''}</button>`;
  if (d.can_edit) {
    document.getElementById('statchip').onclick = e => { e.stopPropagation(); statMenu(e.currentTarget); };
  }
  document.getElementById('dtitle').textContent = d.title;
  document.getElementById('dmeta').innerHTML =
    `<dt>기간</dt><dd class="mono">${d.end && d.end !== d.start ? md(d.start) + ' → ' + md(d.end) : md(d.start)}</dd>
     <dt>담당</dt><dd>${d.department}</dd>
     <dt>상위</dt><dd>${d.parent_title || '—'}</dd>
     <dt>관련팀</dt><dd>${d.related_departments.join(', ') || '—'}</dd>`;

  renderLog();

  let note = '';
  if (d.suggestion_rationale) note += `<div class="note"><b>CLAUDE 제안 근거</b>${esc(d.suggestion_rationale)}</div>`;
  if (d.reclassification_note) note += `<div class="note"><b>분류·담당 변경 기록</b>${esc(d.reclassification_note)}</div>`;
  document.getElementById('dnote').innerHTML = note;
  document.getElementById('daddlog').hidden = !d.can_edit;

  document.getElementById('relN').textContent = d.related.length || '';
  document.getElementById('drel').innerHTML = d.related.length
    ? d.related.map(r => `<div class="relitem">
        <button class="rb" data-rel="${r.run_id}">
          <span class="dot" style="background:${r.color}"></span>${esc(r.title)}
          <span class="rl">${r.kind_label} · ${esc(r.department)}</span></button>
        <div class="menu">
          <button data-act="open">열기<span class="mi">상세</span></button>
          <button data-act="move">이동<span class="mi">보드</span></button></div></div>`).join('')
    : '<div style="font-size:12px;color:var(--ink-3)">연결된 업무 없음</div>';

  calendar(d);
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
}

function renderLog() {
  const entries = detail.discussions;
  const current = entries.filter(e => !e.carried);
  const carried = entries.filter(e => e.carried);
  const line = e => `<div class="entry">
      <span class="d mono">${e.date}</span>
      <span class="${e.superseded ? 'gone' : ''}">${esc(e.body)}</span>
      ${e.author ? `<span class="who">${esc(e.author)}</span>` : ''}</div>`;
  let html = current.length ? current.map(line).join('')
    : '<div class="empty">아직 기록된 논의가 없습니다.</div>';
  if (carried.length) {
    html += `<details class="carried"><summary>지난 회차 논의 ${carried.length}건</summary>
      ${carried.map(line).join('')}</details>`;
  }
  document.getElementById('dlog').innerHTML = html;
}

function closeDrawer() {
  dw.classList.remove('open');
  dw.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('dopen');
  cur = null; detail = null;
  unlink();
}
document.getElementById('dclose').onclick = closeDrawer;
addEventListener('keydown', e => { if (e.key === 'Escape') { closeMenus(); closeDrawer(); } });

document.getElementById('dtabs').onclick = e => {
  const b = e.target.closest('button');
  if (!b) return;
  document.querySelectorAll('#dtabs button').forEach(x => x.setAttribute('aria-selected', x === b));
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.id === 'p-' + b.dataset.p));
};

/* ── 연결된 업무 목록: 열기 / 이동 ── */
function closeMenus() {
  document.querySelectorAll('.menu.on').forEach(m => m.classList.remove('on'));
  document.getElementById('statmenu').classList.remove('on');
}
document.getElementById('drel').onclick = e => {
  const act = e.target.closest('[data-act]');
  if (act) {
    const id = act.closest('.relitem').querySelector('.rb').dataset.rel;
    closeMenus();
    if (act.dataset.act === 'open') { openDrawer(id); link(id); }
    else {
      goTo(id);
      setTimeout(() => {
        const el = findBar(id);
        if (el) el.animate([{opacity: 1}, {opacity: .35}, {opacity: 1}], {duration: 520, iterations: 2});
      }, 300);
    }
    return;
  }
  const rb = e.target.closest('.rb');
  if (rb) {
    const menu = rb.nextElementSibling, was = menu.classList.contains('on');
    closeMenus();
    menu.classList.toggle('on', !was);
  }
};

/* ── 상태 변경 ── */
function statMenu(btn) {
  const menu = document.getElementById('statmenu'), r = btn.getBoundingClientRect();
  menu.innerHTML = Object.entries(STATUS).map(([key, v]) =>
    `<button data-s="${key}"><span class="cv" style="background:${v.color}"></span>${v.label}</button>`).join('');
  menu.style.left = r.left + 'px';
  menu.style.top = (r.bottom + 4) + 'px';
  menu.classList.add('on');
  menu.onclick = async e => {
    const b = e.target.closest('[data-s]');
    if (!b) return;
    closeMenus();
    await setStatus(cur, b.dataset.s);
  };
}

async function setStatus(runId, status) {
  const res = await fetch(`/board/task/${runId}/status`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status}),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '상태를 바꾸지 못했습니다.'); return; }
  const view = await res.json();

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
  const mdate = sheet.querySelector(`.row[data-run="${runId}"] .mdate i`);
  if (mdate) mdate.style.background = view.border;
  if (detail) { detail.status = status; renderDrawer(); }
  applyFilters();
}

/* ── 논의 추가 ── */
document.getElementById('dsave').onclick = async () => {
  const box = document.getElementById('dbody');
  const body = box.value.trim();
  if (!body || !cur) return;
  const supersede = document.getElementById('dsuper').checked;
  const own = detail.discussions.filter(e => !e.carried && !e.superseded);
  const target = supersede && own.length ? own[own.length - 1].id : null;

  const res = await fetch(`/board/task/${cur}/discussion`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({body, supersedes_entry_id: target}),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '저장하지 못했습니다.'); return; }
  const data = await res.json();
  detail.discussions = data.discussions;
  box.value = '';
  document.getElementById('dsuper').checked = false;
  renderLog();
};

/* ── 달력 ── */
function calendar(d) {
  const el = document.getElementById('dcal');
  if (!d.start) { el.innerHTML = ''; return; }
  const [sy, sm, sd] = d.start.split('-').map(Number);
  const [ey, em, ed] = (d.end || d.start).split('-').map(Number);
  const s = new Date(sy, sm - 1, sd), e = new Date(ey, em - 1, ed);
  const marks = {};
  d.related.forEach(r => {
    if (r.start) (marks[r.start] = marks[r.start] || []).push(r.color);
    if (r.end && r.end !== r.start) (marks[r.end] = marks[r.end] || []).push(r.color);
  });
  let out = '';
  const cursor = new Date(s.getFullYear(), s.getMonth(), 1);
  const last = new Date(e.getFullYear(), e.getMonth(), 1);
  while (cursor <= last) {
    const y = cursor.getFullYear(), m = cursor.getMonth();
    out += `<div class="cm">${y}년 ${m + 1}월</div>`;
    WD.forEach((w, i) => out += `<div class="wd${i === 0 ? ' s' : ''}">${w}</div>`);
    const first = new Date(y, m, 1).getDay(), days = new Date(y, m + 1, 0).getDate();
    for (let i = 0; i < first; i++) out += '<div class="dcell pad"></div>';
    for (let day = 1; day <= days; day++) {
      const dt = new Date(y, m, day);
      const iso = `${y}-${String(m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const inRange = dt >= s && dt <= e;
      const edge = iso === d.start || iso === d.end;
      const cls = ['dcell', inRange ? 'in' : '', edge ? (d.status === '지연' ? 'late' : 'edge') : '']
        .filter(Boolean).join(' ');
      const dots = (marks[iso] || []).slice(0, 4).map(c => `<i style="background:${c}"></i>`).join('');
      out += `<div class="${cls}">${day}<span class="dots">${dots}</span></div>`;
    }
    cursor.setMonth(cursor.getMonth() + 1);
  }
  el.innerHTML = out;
}

/* ── 폭 조절 ── */
const grip = document.getElementById('grip');
grip.addEventListener('mousedown', e => {
  e.preventDefault();
  const sx = e.clientX, sw = dw.offsetWidth;
  let moved = false;
  dw.classList.add('sizing');
  document.body.classList.add('sizing');
  const move = ev => {
    if (Math.abs(ev.clientX - sx) > 2) moved = true;
    const w = Math.min(Math.min(900, innerWidth * .7), Math.max(320, sw + (sx - ev.clientX)));
    document.documentElement.style.setProperty('--dw', w + 'px');
  };
  const up = () => {
    dw.classList.remove('sizing');
    document.body.classList.remove('sizing');
    if (moved) dragEnd = Date.now();     // 드래그 끝의 클릭을 '빈 영역 클릭'으로 오해하지 않게
    drawWires();
    removeEventListener('mousemove', move);
    removeEventListener('mouseup', up);
  };
  addEventListener('mousemove', move);
  addEventListener('mouseup', up);
});

/* ── 보드 클릭 ── */
sheet.addEventListener('click', e => {
  if (Date.now() - dragEnd < 400) return;
  const go = e.target.closest('[data-go]');
  if (go) { goTo(go.dataset.go); return; }
  const bar = e.target.closest('.bar[data-run]');
  if (bar) { link(bar.dataset.run); openDrawer(bar.dataset.run); }
});
sheet.addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const bar = e.target.closest('.bar[data-run]');
  if (bar) { e.preventDefault(); link(bar.dataset.run); openDrawer(bar.dataset.run); }
});

addEventListener('click', e => {
  if (Date.now() - dragEnd < 400) return;
  if (!e.target.closest('.relitem') && !e.target.closest('#statmenu') && !e.target.closest('#statchip')) closeMenus();
  if (!dw.classList.contains('open')) return;
  if (e.target.closest('#drawer') || e.target.closest('#statmenu')) return;
  if (e.target.closest('[data-run],[data-go]')) return;
  if (e.target.closest('header') || e.target.closest('.toolbar')) return;
  closeDrawer();
});

drawGrid();
applyFilters();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { drawGrid(); drawWires(); });
})();
