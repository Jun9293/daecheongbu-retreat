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
/* 사용자가 직접 펴거나 접은 부서. 소속 기준 자동 접기보다 이 뜻이 우선한다 —
   상태를 바꿀 때마다 보고 있던 그룹이 닫히면 일을 할 수가 없다. */
const openedByHand = new Map();

const headers = () => [...sheet.querySelectorAll('.row.head .hc')];
const labelW = () => sheet.querySelector('.hlbl').offsetWidth;
const md = iso => iso ? iso.slice(5).replace('-', '/') : '';

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
  if (isMobile()) { openDrawer(runId); return; }
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
addEventListener('resize', () => { drawGrid(); layoutLabels(); drawWires(); });

/* ── 상세 패널 ── */
async function openDrawer(runId) {
  cur = runId;
  const m = META[runId] || {};
  selectTab('rules');   // 열면 업무 규칙이 먼저 (CLAUDE.md 4-9)
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
  const teams = (d.departments || []).map(t =>
    `<option value="${t.key}" data-color="${t.color}" ${t.key === d.department_key ? 'selected' : ''}>${esc(t.name)}</option>`).join('');
  const people = (d.candidates || []).map(p =>
    `<option value="${p.id}" ${p.id === d.assignee_id ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
  document.getElementById('dmeta').innerHTML =
    `<dt>기간</dt><dd>${d.can_edit
        ? `<span class="pill dates">
             <input type="date" id="dstart" value="${d.start || ''}" aria-label="시작일">
             <i class="sep"></i>
             <input type="date" id="dend" value="${d.end || d.start || ''}" aria-label="마감일">
             <b class="span" id="dspan">${spanLabel(d.start, d.end)}</b></span>`
        : `<span class="pill flat"><span class="mono">${
             d.end && d.end !== d.start ? md(d.start) + ' → ' + md(d.end) : md(d.start)}</span>
             <b class="span">${spanLabel(d.start, d.end)}</b></span>`}</dd>
     <dt>담당팀</dt><dd>${d.can_edit
        ? `<span class="pill person"><i class="dot" id="ddeptdot" style="background:${d.department_color}"></i>
             <select id="ddept"><option value="">담당 없음</option>${teams}</select></span>`
        : `<span class="pill flat person"><i class="dot" style="background:${d.department_color}"></i>${esc(d.department)}</span>`}</dd>
     <dt>담당자</dt><dd>${d.can_edit
        ? `<span class="pill person"><select id="dassignee"><option value="">지정 안 함</option>${people}</select></span>`
        : `<span class="pill flat person">${esc(d.assignee || '지정 안 함')}</span>`}</dd>
     <dt>상위</dt><dd>${d.parent_title ? esc(d.parent_title) : '—'}</dd>
     <dt>관련팀</dt><dd>${d.related_departments.map(esc).join(', ') || '—'}</dd>`;

  if (d.can_edit) {
    const start = document.getElementById('dstart'), end = document.getElementById('dend');
    const saveDates = async () => {
      if (!start.value) return;
      if (end.value && end.value < start.value) { end.value = start.value; }
      const res = await fetch(`/board/task/${d.run_id}/dates`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({start: start.value, end: end.value || start.value}),
      });
      if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '기간을 바꾸지 못했습니다.'); return; }
      const saved = await res.json();
      const span = document.getElementById('dspan');
      if (span) span.textContent = spanLabel(saved.start, saved.end);
      applySavedDates(d.run_id, saved);
    };
    start.onchange = saveDates;
    end.onchange = saveDates;

    // 날짜 칸을 누르면 달력이 열린다 (아이콘 없이)
    [start, end].forEach(input => {
      input.onclick = () => { try { input.showPicker(); } catch (err) { /* 지원 안 하면 기본 동작 */ } };
    });

    document.getElementById('ddept').onchange = async e => {
      const key = e.target.value;
      const res = await fetch(`/board/task/${d.run_id}/department`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key: key || null}),
      });
      if (!res.ok) {
        alert((await res.json().catch(() => ({}))).detail || '담당팀을 바꾸지 못했습니다.');
        e.target.value = d.department_key || '';
        return;
      }
      // 업무가 다른 부서의 줄로 옮겨간다 — 보드를 다시 그려야 한다
      location.reload();
    };

    document.getElementById('dassignee').onchange = async e => {
      const value = e.target.value;
      const res = await fetch(`/board/task/${d.run_id}/assignee`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: value ? Number(value) : null}),
      });
      if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '지정하지 못했습니다.'); return; }
      const saved = await res.json();
      detail.assignee_id = saved.assignee_id;
      detail.assignee = saved.assignee;
      applyAssignee(d.run_id, saved.assignee);
    };
  }

  renderLog();
  renderRules();

  let note = '';
  if (d.suggestion_rationale) note += `<div class="note"><b>CLAUDE 제안 근거</b>${esc(d.suggestion_rationale)}</div>`;
  if (d.reclassification_note) note += `<div class="note"><b>분류·담당 변경 기록</b>${esc(d.reclassification_note)}</div>`;
  document.getElementById('dnote').innerHTML = note;
  document.getElementById('daddlog').hidden = !d.can_edit;

  renderRel(d);

  calendar(d);
}


/* ── 연결된 업무: 선행 / 후속 / 관련 ────────────────────────────────
   셋을 한 덩어리로 그리면 무엇이 나를 막는지 읽히지 않는다.
   선행은 방향이 있고 '기다리는 쪽'에만 저장한다. 후속은 그 역방향을
   서버가 계산한 것이라 여기서 직접 고치지 않는다 — 고치려면 그쪽 업무를
   열어야 한다. 관계는 회차가 아니라 라이브러리에 붙으므로 다음 회차에도 간다. */
function relItem(r) {
  return `<div class="relitem">
    <button class="rb" data-rel="${r.run_id}">
      <span class="dot" style="background:${r.color}"></span>${esc(r.title)}
      <span class="rl">${r.kind_label} · ${esc(r.department)}</span></button>
    <div class="menu">
      <button data-act="open">열기<span class="mi">상세</span></button>
      <button data-act="move">이동<span class="mi">보드</span></button></div></div>`;
}

function renderRel(d) {
  const pre = d.prerequisites || [], dep = d.dependents || [], rel = d.related || [];
  document.getElementById('relN').textContent = (pre.length + dep.length + rel.length) || '';

  const section = (title, rows, hint, edit) => `<div class="relsec">
    <h4>${title}<span class="n">${rows.length}</span>${
      edit ? '<button class="edit" id="preedit">고치기</button>' : ''}</h4>
    ${rows.length ? rows.map(relItem).join('')
      : `<div class="relnone">${hint}</div>`}</div>`;

  document.getElementById('drel').innerHTML =
    section('선행 — 끝나야 시작할 수 있다', pre, '기다리는 업무 없음', d.can_edit) +
    section('후속 — 나를 기다린다', dep, '나를 기다리는 업무 없음', false) +
    section('관련 — 방향 없음', rel, '연결된 업무 없음', false) +
    `<div class="relnote">선후행은 회차가 아니라 <b>업무 자체</b>에 붙습니다 —
      업무 규칙과 같이 <b>다음 회차에도 그대로 적용됩니다.</b>
      후속은 저장하지 않고 선행의 역방향으로 계산합니다.</div>`;

  const edit = document.getElementById('preedit');
  if (edit) edit.onclick = () => openPrereqPicker(d);
}

/* 선행 고르기 — 이 업무가 기다릴 업무를 고른다 */
function openPrereqPicker(d) {
  const chosen = new Set((d.prerequisites || []).map(r => r.run_id));
  const box = document.getElementById('prepick');
  box.innerHTML = `<div class="sheetbox">
    <div class="sh"><b>${esc(d.title)} 이(가) 기다릴 업무</b>
      <button type="button" class="btn sm" data-close="1">닫기</button></div>
    <p class="sechint" id="prepickwarn" hidden></p>
    <input type="search" class="find" id="prepickfind" placeholder="이름으로 좁혀 찾기" autocomplete="off">
    <div class="plist" id="prepicklist">${(d.link_candidates || []).map(c =>
      `<label data-name="${esc(c.title)}">
        <input type="checkbox" value="${c.run_id}" ${chosen.has(c.run_id) ? 'checked' : ''}>
        <span>${esc(c.title)}</span><span class="dw">D-${c.d_week}주</span></label>`).join('')}</div>
    <div class="sh end">
      <button type="button" class="btn pri" id="prepicksave">저장</button>
      <button type="button" class="btn" data-close="1">취소</button></div></div>`;
  box.hidden = false;

  document.getElementById('prepickfind').oninput = e => {
    const q = e.target.value.trim().toLowerCase();
    box.querySelectorAll('#prepicklist label').forEach(el => {
      el.hidden = q ? !el.dataset.name.toLowerCase().includes(q) : false;
    });
  };
  box.onclick = e => {
    if (e.target === box || e.target.closest('[data-close]')) box.hidden = true;
  };
  document.getElementById('prepicksave').onclick = async () => {
    const ids = [...box.querySelectorAll('#prepicklist input:checked')].map(i => Number(i.value));
    const res = await fetch(`/board/task/${cur}/prerequisites`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({run_ids: ids}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const warn = document.getElementById('prepickwarn');
      warn.textContent = data.detail || '저장하지 못했습니다.';
      warn.hidden = false;
      warn.style.color = 'var(--now-ink, #8E2A19)';
      return;
    }
    box.hidden = true;
    detail = data;
    renderRel(detail);
  };
}

/* 며칠짜리인지 한눈에 — 날짜만 보고 세지 않게 */
function spanLabel(start, end) {
  if (!start) return '';
  const a = new Date(start), b = new Date(end || start);
  const days = Math.round((b - a) / 864e5) + 1;
  return days > 1 ? days + '일' : '하루';
}
/* ── 업무 규칙 ── */
function renderRules() {
  const box = document.getElementById('drules');
  const text = (detail.rules || '').trim();
  box.innerHTML = text
    ? `<div class="ruletext">${esc(text)}</div>`
    : '<div class="empty">아직 적어 둔 규칙이 없습니다.</div>';
  if (detail.can_edit) {
    box.insertAdjacentHTML('beforeend',
      `<button class="ruleedit" id="drulesopen">${text ? '규칙 고치기' : '규칙 적기'}</button>`);
    document.getElementById('drulesopen').onclick = () => {
      document.getElementById('drulesbody').value = detail.rules || '';
      document.getElementById('drulesedit').hidden = false;
      document.getElementById('drules').hidden = true;
      document.getElementById('drulesbody').focus();
    };
  }
  document.getElementById('drulesedit').hidden = true;
  box.hidden = false;
}

document.getElementById('drulescancel').onclick = () => {
  document.getElementById('drulesedit').hidden = true;
  document.getElementById('drules').hidden = false;
};

document.getElementById('drulessave').onclick = async () => {
  const body = document.getElementById('drulesbody').value;
  const res = await fetch(`/board/task/${cur}/rules`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({body}),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '저장하지 못했습니다.'); return; }
  detail.rules = (await res.json()).rules;
  renderRules();
};

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
}

function renderLog() {
  const entries = detail.discussions;
  // 대체된 기록과 후속 내용을 한 덩어리로 잇는다 — 기존 내용에 취소선,
  // 그 아래에 수정 내용을 붙이는 노션 관례 (CLAUDE.md 4-9)
  const replacement = new Map();
  entries.forEach(e => { if (e.replaces) replacement.set(e.replaces, e); });

  const chainOf = start => {
    const out = [start];
    let next = replacement.get(start.id);
    while (next) { out.push(next); next = replacement.get(next.id); }
    return out;
  };
  const line = start => {
    const chain = chainOf(start);
    const last = chain[chain.length - 1];
    const body = chain.map((node, i) => {
      const struck = i < chain.length - 1;
      const text = struck ? `<s>${esc(node.body)}</s>` : esc(node.body);
      const pen = node.can_edit
        ? `<button class="editline" data-edit="${node.id}" title="이 기록 고치기">수정</button>` : '';
      const when = i > 0 && node.date && node.date !== start.date
        ? ` <span class="d mono">${node.date}</span>` : '';
      return `<span class="${i === 0 ? 'body' : 'fix'}" data-entry="${node.id}">${text}${when}${pen}</span>`;
    }).join('');
    // 날짜는 본문 위에 따로 둔다 — 옆에 붙이면 번호 매긴 목록의 첫 줄만 밀려
    // 둘째 줄부터와 왼쪽 끝이 어긋난다.
    return `<div class="entry"><div class="ehead"><span class="d mono">${start.date}</span>` +
      `${last.author ? `<span class="who">${esc(last.author)}</span>` : ''}</div>${body}</div>`;
  };

  const roots = entries.filter(e => !e.replaces);
  const current = roots.filter(e => !e.carried);
  const carried = roots.filter(e => e.carried);
  let html = current.length ? current.map(line).join('')
    : '<div class="empty">아직 기록된 논의가 없습니다.</div>';
  if (carried.length) {
    html += `<details class="carried"><summary>지난 회차 논의 ${carried.length}건</summary>
      ${carried.map(line).join('')}</details>`;
  }
  document.getElementById('dlog').innerHTML = html;
}

/* 써 놓은 논의를 그 자리에서 고친다. 말을 바꾸는 것(취소선 + 후속 기록)과
   잘못 쓴 것을 바로잡는 것은 다르므로, 이건 오타·오기를 위한 자리다. */
document.getElementById('dlog').addEventListener('click', async e => {
  const open = e.target.closest('[data-edit]');
  if (open) { startEntryEdit(open.dataset.edit); return; }

  const cancel = e.target.closest('[data-cancel-edit]');
  if (cancel) { renderLog(); return; }

  const save = e.target.closest('[data-save-edit]');
  if (!save) return;
  const id = save.dataset.saveEdit;
  const box = document.querySelector(`#dlog [data-entry="${id}"] textarea`);
  const body = box.value.trim();
  if (!body) { box.focus(); return; }
  const res = await fetch(`/board/task/${cur}/discussion/${id}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({body}),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '고치지 못했습니다.'); return; }
  detail.discussions = (await res.json()).discussions;
  renderLog();
});

function startEntryEdit(id) {
  const entry = detail.discussions.find(x => String(x.id) === String(id));
  const span = document.querySelector(`#dlog [data-entry="${id}"]`);
  if (!entry || !span) return;
  span.innerHTML = `<textarea class="editbox">${esc(entry.body)}</textarea>
    <span class="editrow">
      <button class="pri" data-save-edit="${id}">저장</button>
      <button data-cancel-edit="1">취소</button></span>`;
  const box = span.querySelector('textarea');
  listEditor(box);
  box.style.height = Math.max(56, box.scrollHeight) + 'px';
  box.focus();
  box.setSelectionRange(box.value.length, box.value.length);
}

function closeDrawer() {
  dw.classList.remove('open');
  dw.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('dopen');
  cur = null; detail = null;
  unlink();
}
document.getElementById('dclose').onclick = closeDrawer;
document.getElementById('dcancelnew').onclick = () => {
  document.getElementById('dbody').value = '';
  document.getElementById('dsuper').checked = false;
};
addEventListener('keydown', e => { if (e.key === 'Escape') { closeMenus(); closeDrawer(); } });

function selectTab(name) {
  document.querySelectorAll('#dtabs button').forEach(x =>
    x.setAttribute('aria-selected', x.dataset.p === name));
  document.querySelectorAll('#drawer .pane').forEach(p =>
    p.classList.toggle('on', p.id === 'p-' + name));
}

document.getElementById('dtabs').onclick = e => {
  const b = e.target.closest('button');
  if (!b) return;
  selectTab(b.dataset.p);
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
  // 같은 배지를 다시 누르면 상태를 바꾸지 않고 목록만 닫는다
  if (menu.classList.contains('on')) { closeMenus(); return; }
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
  document.querySelectorAll(`.mrow[data-run="${runId}"]`).forEach(row => {
    row.dataset.status = status;
    row.classList.toggle('done', status === '완료');
    row.querySelector('.st').style.background = view.border;
    const f = row.querySelector('.flag');
    if (f) f.remove();
    if (status === '지연') row.insertAdjacentHTML('beforeend', '<span class="flag">지연</span>');
  });
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

/* ── 노션처럼 쓰는 입력칸 ──────────────────────────────────────────
   번호를 매기고 엔터를 치면 다음 번호가 자동으로 붙고, 하이픈에 스페이스를
   치면 글머리표가 된다. 탭으로 한 단계 들어가고 시프트+탭으로 나온다.
   빈 항목에서 엔터를 치면 목록을 빠져나온다. */
const BULLETS = ['•', '◦', '▪'];
const LIST_RE = /^(\s*)(?:([•◦▪-])|(\d+)\.)\s(.*)$/;

function lineAt(box) {
  const value = box.value, pos = box.selectionStart;
  const from = value.lastIndexOf('\n', pos - 1) + 1;
  let to = value.indexOf('\n', pos);
  if (to < 0) to = value.length;
  return {from, to, text: value.slice(from, to)};
}

function replaceLine(box, line, text, caret) {
  const value = box.value;
  box.value = value.slice(0, line.from) + text + value.slice(line.to);
  const at = line.from + (caret === undefined ? text.length : caret);
  box.setSelectionRange(at, at);
}

function markerFor(indent, numbered, seed) {
  const depth = Math.floor(indent.length / 2);
  return numbered ? `${seed || 1}.` : BULLETS[Math.min(depth, BULLETS.length - 1)];
}

function listEditor(box) {
  box.addEventListener('keydown', e => {
    const line = lineAt(box);
    const m = line.text.match(LIST_RE);

    if (e.key === 'Enter' && !e.shiftKey && m) {
      const [, indent, bullet, num, body] = m;
      e.preventDefault();
      if (!body.trim()) {                       // 빈 항목 → 목록에서 빠져나온다
        replaceLine(box, line, indent.slice(0, -2));
        return;
      }
      const next = num ? `${indent}${Number(num) + 1}. ` : `${indent}${bullet} `;
      const at = box.selectionStart;
      box.value = box.value.slice(0, at) + '\n' + next + box.value.slice(at);
      const caret = at + 1 + next.length;
      box.setSelectionRange(caret, caret);
      return;
    }

    if (e.key === 'Tab') {
      e.preventDefault();
      if (!m) {                                  // 목록이 아니면 두 칸 들여쓰기
        const at = box.selectionStart;
        if (e.shiftKey) return;
        box.value = box.value.slice(0, at) + '  ' + box.value.slice(at);
        box.setSelectionRange(at + 2, at + 2);
        return;
      }
      const [, indent, bullet, num, body] = m;
      const depth = Math.floor(indent.length / 2);
      const next = e.shiftKey ? Math.max(0, depth - 1) : depth + 1;
      const pad = '  '.repeat(next);
      const marker = num ? '1.' : BULLETS[Math.min(next, BULLETS.length - 1)];
      replaceLine(box, line, `${pad}${marker} ${body}`);
      return;
    }

    if (e.key === ' ') {                         // "- " 나 "* " 를 글머리표로
      const plain = line.text.match(/^(\s*)([-*])$/);
      if (plain && box.selectionStart === line.to) {
        e.preventDefault();
        const depth = Math.floor(plain[1].length / 2);
        replaceLine(box, line, `${plain[1]}${BULLETS[Math.min(depth, BULLETS.length - 1)]} `);
      }
    }
  });
}

document.querySelectorAll('textarea[data-listedit]').forEach(listEditor);

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
    dragEnd = Date.now();                       // 드래그 끝의 클릭을 무시시킨다

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
  if (detail && String(detail.run_id) === String(runId)) {
    detail.start = saved.start;
    detail.end = saved.end;
    renderDrawer();
  }
  layoutLabels();
  drawWires();
}

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

const mlist = document.getElementById('mlist');
if (mlist) mlist.addEventListener('click', e => {
  const row = e.target.closest('.mrow');
  if (row) openDrawer(row.dataset.run);
});

/* 클릭이 어디서 일어났는지는 '누른 순간'에 정해 둔다.
   중간 핸들러가 innerHTML 을 갈아끼우면 눌린 요소가 DOM 에서 떨어져 나가고,
   그 뒤에 closest() 로 물으면 전부 null 이라 '바깥 클릭'으로 오판한다. */
let clickOrigin = null;
addEventListener('click', e => {
  const at = sel => !!(e.target instanceof Element) && !!e.target.closest(sel);
  clickOrigin = {
    drawer: at('#drawer'),
    statmenu: at('#statmenu'),
    statchip: at('#statchip'),
    relitem: at('.relitem'),
    task: at('.bar[data-run],[data-go]'),
    chrome: at('header') || at('.toolbar'),
  };
}, true);

addEventListener('click', () => {
  const from = clickOrigin || {};
  clickOrigin = null;
  if (Date.now() - dragEnd < 400) return;
  if (!from.relitem && !from.statmenu && !from.statchip) closeMenus();
  if (!dw.classList.contains('open')) return;
  if (from.drawer || from.statmenu) return;
  if (from.task) return;                  // 바·업무명은 다른 업무를 여는 동작
  if (from.chrome) return;                // 소속 선택·필터를 만질 때 닫히면 불편하다
  closeDrawer();
});

drawGrid();
applyFilters();
// 글꼴이 로드되기 전에 재면 폭이 틀리므로 다시 계산한다
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { drawGrid(); layoutLabels(); drawWires(); });
}
})();
