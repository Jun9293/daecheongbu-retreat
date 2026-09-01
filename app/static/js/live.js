/* 수련회 진행 (CLAUDE.md 5장).
 *
 * 이 화면은 다른 화면과 조건이 다릅니다 — **현장에서 휴대폰으로 급히 봅니다.**
 * 사람이 뛰어다니면서 한 손으로 누릅니다. 그래서:
 *   · 체크는 한 번 누르면 바로 반영됩니다. 저장 버튼이 없습니다
 *   · 누른 것은 화면에 즉시 반영하고 서버에는 뒤따라 보냅니다.
 *     실패하면 **되돌리고 화면에 말합니다** — 조용히 삼키지 않습니다
 *   · 좁은 화면에서는 목록과 체크리스트를 한 번에 하나씩 보여줍니다
 *
 * 판정(진행 중·지연)은 전부 서버가 계산합니다. 화면이 다시 판단하지 않습니다 —
 * 두 벌이 되면 새로고침할 때마다 답이 달라집니다.
 */
(function () {
'use strict';

const LIVE = JSON.parse(document.getElementById('live-meta').textContent);
const OPTS = JSON.parse(document.getElementById('live-opts').textContent);

const PHASES = [
  ['pre',  '준비', '전', '#4C8A5E', '프로그램 시작 전에 끝나 있어야 하는 것'],
  ['mid',  '진행', '중', '#C4554D', '프로그램이 도는 동안 챙길 것'],
  ['post', '정리', '후', '#787774', '끝나고 반드시 처리할 것'],
];
const PART_COLOR = {
  '행정': '#2F4858', '현장관리': '#4A8A5C', '비품': '#C0782F', '음식': '#B44B42',
  '재정': '#8A6A4F', '교역자': '#7A5BA6', '헤브론': '#4A8A5C', '코람데오': '#B44B42',
};

const detail = document.getElementById('detail');
const rail = document.getElementById('rail');
const wrap = document.getElementById('wrap');
const backrail = document.getElementById('backrail');

let selected = LIVE.selected;
let part = LIVE.default_part || '전체';
// 범위 칩 (5-2). 파트 칩과 함께 걸린다 — 서로 다른 축이다.
let scope = '전체';

const esc = s => String(s == null ? '' : s)
  .replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

const isNarrow = () => matchMedia('(max-width: 820px)').matches;
const current = () => (selected == null ? null : LIVE.programs[selected]);

/* ── 전 / 중 / 후 ──────────────────────────────────────────────────
   **구간이 먼저고 범위가 나중이다** (5-2). 현장에서 먼저 묻는 것은
   "지금 뭘 해야 하나" 이지 "이게 팀 일인가 내 일인가" 가 아니다.
   그래서 준비·진행·정리로 먼저 가르고, 그 안에서 팀·개인으로 나눈다. */
const AUD_LABEL = Object.fromEntries((OPTS.audiences || []).map(o => [o.value, o.label]));
const TRACK_LABEL = Object.fromEntries((OPTS.tracks || []).map(o => [o.value, o.label]));

function renderDetail() {
  const p = current();
  if (!p) { detail.innerHTML = ''; return; }

  const usedParts = [...new Set(p.items.map(i => i.part))];
  const partChips = ['전체'].concat(LIVE.parts.filter(k => usedParts.includes(k)));
  const usedScopes = [...new Set(p.items.map(i => i.scope))];
  const stateLabel = {live: '진행 중', done: '지남', todo: '예정'}[p.state];

  /* 셋(누가 함께하나·어떤 일인가·나란히 도는가)을 여기 보여 준다. 봉사자
     시간표에서 이 프로그램이 어느 칸에 서는지가 이 셋으로 정해지는데(5-8),
     화면에 안 보이면 틀렸는지 알 길이 없다. */
  const shape = [
    AUD_LABEL[p.audience] || p.audience,
    TRACK_LABEL[p.track] || p.track,
  ].concat(p.parallel ? ['나란히'] : []).join(' · ');

  let h = `<div class="dh"><h1>${esc(p.name)}</h1>
      <span class="when mono">${esc(p.start_time)}${
        p.end_time ? `–${esc(p.end_time)}` : ''}</span>
      ${OPTS.can_manage ? '<button class="btn ghost sm" id="editpgm" type="button">고치기</button>' : ''}
      </div>
    <div class="dmeta">
      ${p.host ? `<span><b>담당</b>${esc(p.host)}</span>` : ''}
      ${p.place ? `<span><b>장소</b>${esc(p.place)}</span>` : ''}
      ${p.note ? `<span><b>운영</b>${esc(p.note)}</span>` : ''}
      <span><b>구분</b>${esc(shape)}</span>
      <span><b>상태</b>${stateLabel}</span></div>`;

  if (p.state === 'live') {
    h += `<div class="note"><b>지금 진행 중입니다.</b> 아래 <b>진행</b> 항목을 먼저 확인하세요.
      끝나면 <b>정리</b> 항목이 다음 프로그램 준비와 겹치지 않도록 바로 처리해야 합니다.</div>`;
  } else if (p.leftover_post && !LIVE.carried_only) {
    // 넘어가면 사라지는 자리다 — 그래서 여기서 한 번 더 말한다
    h += `<div class="note warn"><b>끝났는데 정리 항목이 ${p.leftover_post}건 남았습니다.</b>
      다음 프로그램 준비와 겹치면 그대로 누락됩니다.</div>`;
  }

  /* 칩 두 줄 — 파트(무슨 일인가)와 범위(팀이 움직이는가 내가 하는가)는
     서로 다른 축이라 **함께 걸린다.** 한 줄에 섞으면 어느 것이 어느 축인지
     읽히지 않는다. 범위 칩은 그 프로그램에 두 종류가 다 있을 때만 낸다. */
  h += `<div class="filters">` + partChips.map(k =>
    `<button type="button" data-part="${esc(k)}" aria-pressed="${part === k}">${
      k === '전체' ? '' : `<i style="background:${PART_COLOR[k] || '#787774'}"></i>`}${esc(k)}</button>`
  ).join('') + `</div>`;

  if (usedScopes.length > 1) {
    h += `<div class="filters scopes">
      <button type="button" data-scope="전체" aria-pressed="${scope === '전체'}">전체</button>
      <button type="button" data-scope="team" aria-pressed="${scope === 'team'}">팀 단위만</button>
      <button type="button" data-scope="person" aria-pressed="${scope === 'person'}">내 것만</button>
    </div>`;
  }

  PHASES.forEach(([key, name, tag, color, hint]) => {
    const rows = p.items.filter(i => i.phase === key);
    const shown = rows.filter(i =>
      (part === '전체' || i.part === part) && (scope === '전체' || i.scope === scope));
    const done = rows.filter(i => i.done).length;
    h += `<div class="phase ph-${key}"><div class="ph-h">
      <h2><span class="tag" style="--tagc:${color}">${tag}</span>${name}</h2>
      <span class="hint">${hint}</span>
      <span class="n mono">${done}/${rows.length}</span></div>`;

    if (!rows.length) {
      h += `<div class="empty">등록된 항목이 없습니다.</div>`;
    } else if (!shown.length) {
      h += `<div class="empty">${filterWord()} 맡은 항목이 없습니다.</div>`;
    } else {
      // 팀이 움직여야 개인 일이 돌아간다 — 팀 단위를 위에 둔다.
      // 한쪽이 비면 그 라벨도 내지 않는다 (라벨만 있는 빈 칸은 잡음이다).
      [['team', '팀 단위'], ['person', '개인 단위']].forEach(([kind, label]) => {
        const part_ = shown.filter(i => i.scope === kind);
        if (!part_.length) return;
        h += `<div class="scopegroup sg-${kind}">
          <div class="sg-h">${label}<span class="n mono">${part_.length}</span></div>
          ${part_.map(i => itemRow(i, p, key)).join('')}</div>`;
      });
    }

    if (OPTS.can_manage) {
      h += `<button class="itemadd" type="button" data-add="${key}">+ ${name} 항목</button>`;
    }
    h += `</div>`;
  });

  detail.innerHTML = h;
  detail.scrollTop = 0;
}

/* 걸린 필터를 사람 말로 — "현장관리 파트가", "팀 단위가", "현장관리 파트의 개인 단위가" */
function filterWord() {
  const bits = [];
  if (part !== '전체') bits.push(`${part} 파트`);
  if (scope !== '전체') bits.push(scope === 'team' ? '팀 단위' : '개인 단위');
  return (bits.join('의 ') || '조건에 맞는 항목') + '가';
}

function itemRow(item, program, phase) {
  // 지연은 서버가 준 판정을 그대로 쓴다 — 시작했는데 준비가 안 끝난 것.
  // 시스템 밖에서 진행한 회차(5-6)에는 붙이지 않는다 — 안 끝난 게 아니라
  // 누른 적이 없는 것이라, 위의 안내와 아래의 빨간 배지가 서로를 부정한다.
  const late = !LIVE.carried_only && phase === 'pre' && !item.done
    && (program.state === 'live' || program.state === 'done');
  // 팀 단위는 담당 이름을 앞세우고, 개인 단위는 이름을 앞세운다 —
  // 팀은 "누가 움직이나" 가 먼저고, 개인은 "누구 일인가" 가 먼저다
  const who = esc(item.assignee || '');
  return `<div class="item${item.done ? ' on' : ''}" data-item="${item.id}">
    <button class="tick" type="button" data-tick="${item.id}"
      aria-pressed="${item.done}" aria-label="${item.done ? '완료 취소' : '완료'}">
      <span class="box"></span></button>
    <span class="txt">${item.scope === 'person' && who ? `<b class="lead">${who}</b> ` : ''}${esc(item.text)}
      ${item.done && item.done_at
        ? `<em class="stamp mono">${esc(item.done_at)}${item.done_by ? ' · ' + esc(item.done_by) : ''}</em>`
        : ''}</span>
    ${late ? '<span class="flag">지연</span>' : ''}
    <span class="who">
      <span class="part" style="--partc:${PART_COLOR[item.part] || '#787774'}">${esc(item.part)}</span>
      ${item.scope === 'team' && who ? `<span class="as">${who}</span>` : ''}</span>
    ${OPTS.can_manage ? `<button class="scopeswap" type="button" data-scopeswap="${item.id}"
      title="${item.scope === 'team' ? '개인 단위로' : '팀 단위로'} 옮기기">${
        item.scope === 'team' ? '팀' : '개인'}</button>` : ''}
    ${OPTS.can_manage ? `<button class="itemdel" type="button" data-del="${item.id}" aria-label="항목 삭제">×</button>` : ''}
  </div>`;
}

/* ── 왼쪽 목록의 숫자·배지만 갱신한다 (전체를 다시 그리면 스크롤을 잃는다) ── */
function refreshRail(programId) {
  const p = LIVE.programs.find(x => x.id === programId);
  if (!p || !rail) return;
  const done = p.items.filter(i => i.done).length;
  p.done = done;
  const started = p.state === 'live' || p.state === 'done';
  // 시스템 밖에서 진행한 회차에는 지연도 남은 정리도 세지 않는다 (5-6)
  p.late = LIVE.carried_only || !started
    ? 0 : p.items.filter(i => i.phase === 'pre' && !i.done).length;
  p.leftover_post = LIVE.carried_only || p.state !== 'done'
    ? 0 : p.items.filter(i => i.phase === 'post' && !i.done).length;

  const ct = rail.querySelector(`[data-ct="${p.id}"]`);
  if (ct) ct.textContent = `${done}/${p.total}`;

  const btn = rail.querySelector(`[data-pgm="${p.id}"]`);
  if (!btn) return;
  const body = btn.querySelector('.b');
  let flag = btn.querySelector(`[data-late="${p.id}"]`);
  if (p.late && !flag) {
    flag = document.createElement('span');
    flag.className = 'flag';
    flag.dataset.late = p.id;
    flag.textContent = '지연';
    btn.insertBefore(flag, ct);
  } else if (!p.late && flag) flag.remove();

  let left = btn.querySelector(`[data-left="${p.id}"]`);
  if (p.leftover_post) {
    if (!left) {
      left = document.createElement('span');
      left.className = 'left';
      left.dataset.left = p.id;
      body.appendChild(left);
    }
    left.textContent = `정리 ${p.leftover_post}건 남음`;
  } else if (left) left.remove();

  // 당일 진행률. 안내 문구가 있는 회차(체크 0건인 지난 회차)는 막대가 없다 —
  // 누군가 체크를 하나 누르면 그때 새로고침되며 막대로 바뀐다.
  const bar = document.querySelector('.days .bar i');
  const label = document.querySelector('.days .prog b');
  if (bar && label) {
    let d = 0, t = 0;
    LIVE.programs.forEach(x => { d += x.items.filter(i => i.done).length; t += x.total; });
    bar.style.width = (t ? d / t * 100 : 0) + '%';
    label.textContent = `${d}/${t}`;
  }
}

/* ── 체크 ─────────────────────────────────────────────────────────
   누른 것을 화면에 먼저 반영하고 서버에는 뒤따라 보낸다. 현장 네트워크가
   느려도 손이 멈추지 않아야 하기 때문이다. 실패하면 되돌리고 말한다 —
   조용히 삼키면 눌렀다고 믿은 채로 넘어간다. */
async function toggle(itemId) {
  const p = current();
  if (!p) return;
  const item = p.items.find(i => i.id === Number(itemId));
  if (!item || item.busy) return;

  const was = item.done;
  item.done = !was;
  item.busy = true;
  if (!item.done) { item.done_at = null; item.done_by = null; }
  renderDetail();
  refreshRail(p.id);

  try {
    const res = await fetch(`/live/item/${itemId}/check`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({done: item.done}),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `저장하지 못했습니다 (${res.status})`);
    }
    const saved = await res.json();
    Object.assign(item, saved.item, {busy: false});
  } catch (err) {
    item.done = was;                       // 되돌린다
    item.busy = false;
    say(`${item.text} — ${err.message || '저장하지 못했습니다.'} 다시 눌러주세요.`);
  }
  item.busy = false;
  renderDetail();
  refreshRail(p.id);
}

/* 실패를 화면에 말한다. 현장에서는 콘솔을 아무도 안 본다. */
let sayBox = null;
function say(text) {
  if (!sayBox) {
    sayBox = document.createElement('div');
    sayBox.className = 'livewarn';
    sayBox.setAttribute('role', 'alert');
    document.body.appendChild(sayBox);
    sayBox.onclick = () => { sayBox.remove(); sayBox = null; };
  }
  sayBox.textContent = text;
}

/* ── 고르기 ── */
function select(index) {
  selected = index;
  rail && rail.querySelectorAll('[data-pgm]').forEach(b =>
    b.setAttribute('aria-current', Number(b.dataset.i) === index));
  const p = current();
  part = LIVE.parts.includes(part) || part === '전체' ? part : '전체';
  renderDetail();
  if (isNarrow()) showDetail(true);
  const btn = rail && rail.querySelector('[aria-current="true"]');
  if (btn && !isNarrow()) btn.scrollIntoView({block: 'nearest'});
}

/* 좁은 화면 — 목록과 체크리스트를 한 번에 하나씩 */
function showDetail(on) {
  if (!wrap) return;
  wrap.classList.toggle('showdetail', !!on);
  if (backrail) backrail.hidden = !on || !isNarrow();
}

if (rail) rail.addEventListener('click', e => {
  const btn = e.target.closest('[data-pgm]');
  if (btn) { select(Number(btn.dataset.i)); return; }
});

if (backrail) backrail.onclick = () => showDetail(false);
addEventListener('resize', () => {
  if (!isNarrow()) { showDetail(false); if (backrail) backrail.hidden = true; }
  else if (backrail) backrail.hidden = !wrap.classList.contains('showdetail');
});

detail && detail.addEventListener('click', e => {
  const tick = e.target.closest('[data-tick]');
  if (tick) { toggle(tick.dataset.tick); return; }
  if (e.target.closest('#editpgm')) { openProgramForm(current()); return; }
  const chip = e.target.closest('[data-part]');
  if (chip) { part = chip.dataset.part; renderDetail(); return; }
  const sc = e.target.closest('[data-scope]');
  if (sc) { scope = sc.dataset.scope; renderDetail(); return; }
  const add = e.target.closest('[data-add]');
  if (add) { addItem(add.dataset.add); return; }
  const del = e.target.closest('[data-del]');
  if (del) { removeItem(del.dataset.del); return; }
  const sw = e.target.closest('[data-scopeswap]');
  if (sw) { swapScope(sw.dataset.scopeswap); return; }
});

/* 추측이 틀렸으면 그 자리에서 바꾼다 (5-2) */
async function swapScope(itemId) {
  const p = current();
  const item = p.items.find(i => i.id === Number(itemId));
  if (!item) return;
  const next = item.scope === 'team' ? 'person' : 'team';
  const res = await fetch(`/live/item/${itemId}/scope`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scope: next}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { say(data.detail || '바꾸지 못했습니다.'); return; }
  Object.assign(item, data.item);
  renderDetail();
}

/* ── 총무팀: 항목·프로그램 짜기 ── */
async function addItem(phase) {
  const p = current();
  const text = prompt(`${{'pre': '준비', 'mid': '진행', 'post': '정리'}[phase]} 항목 내용`);
  if (!text) return;
  const partKey = prompt(`파트 (${OPTS.parts.join(' / ')})`, part === '전체' ? OPTS.parts[0] : part);
  if (!partKey) return;
  const who = prompt('담당자 이름 (비워도 됩니다)', '') || '';
  // 범위는 파트·담당으로 추측해 보여주되 **바꿀 수 있다** — 추측이지 규칙이 아니다.
  // 총무팀 항목에도 "강당 의자 세팅_전체" 같은 팀 단위가 섞인다 (5-2).
  const guess = OPTS.team_parts.includes(partKey) || !who.trim()
    || OPTS.team_words.includes(who.trim()) ? 'team' : 'person';
  const picked = prompt(
    `범위 — team(팀이 통째로 움직임) / person(개인에게 붙음)`, guess);
  if (!picked) return;
  const res = await fetch(`/live/program/${p.id}/item`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({phase, part_key: partKey, assignee_name: who, text,
                          scope: picked.trim()}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { say(data.detail || '추가하지 못했습니다.'); return; }
  p.items.push(data.item);
  p.total += 1;
  renderDetail();
  refreshRail(p.id);
}

async function removeItem(itemId) {
  const p = current();
  const item = p.items.find(i => i.id === Number(itemId));
  if (!item || !confirm(`"${item.text}" 을(를) 지웁니다.`)) return;
  const res = await fetch(`/live/item/${itemId}/delete`, {method: 'POST'});
  if (!res.ok) { say('지우지 못했습니다.'); return; }
  p.items = p.items.filter(i => i.id !== Number(itemId));
  p.total -= 1;
  renderDetail();
  refreshRail(p.id);
}

/* 프로그램 만들기·고치기 (5-1).
 *
 * prompt() 를 줄줄이 띄우던 것을 창 하나로 바꾼다. audience·track·parallel
 * 셋이 더 생겼는데, 이 셋은 **뜻을 옆에 적어 주지 않으면 고를 수가 없다** —
 * `staff` 를 보고 무엇인지 아는 사람은 이걸 만든 사람뿐이다.
 * 기본값은 가장 흔한 경우다: 참가자와 함께하는 정규일정.
 */
function pgmDefaults() {
  return {
    id: null, name: '', day: LIVE.day || OPTS.days[0], start_time: '09:00',
    end_time: '', host: '', place: '', note: '',
    audience: 'all', track: 'main', parallel: false,
  };
}

function radioRow(field, options, chosen) {
  return options.map(o => `
    <label class="pick">
      <input type="radio" name="${field}" value="${o.value}"
             ${o.value === chosen ? 'checked' : ''}>
      <span class="pick-l">${o.label}</span>
      <span class="pick-h">${o.hint}</span>
    </label>`).join('');
}

function openProgramForm(source) {
  const p = Object.assign(pgmDefaults(), source || {});
  const box = document.getElementById('pgmedit');
  const editing = p.id != null;
  box.innerHTML = `
    <div class="sheetform" role="dialog" aria-modal="true"
         aria-label="${editing ? '프로그램 고치기' : '프로그램 추가'}">
      <h3>${editing ? '프로그램 고치기' : '프로그램 추가'}</h3>
      <div class="frow">
        <label>이름<input id="f-name" value="${p.name}" autofocus></label>
      </div>
      <div class="frow">
        <label>일자<select id="f-day">${OPTS.days.map(d =>
          `<option ${d === p.day ? 'selected' : ''}>${d}</option>`).join('')}</select></label>
        <label>시작<input id="f-start" value="${p.start_time}" placeholder="09:30"></label>
        <label>끝<input id="f-end" value="${p.end_time || ''}" placeholder="비워도 됩니다"></label>
      </div>
      <div class="frow">
        <label>담당<input id="f-host" value="${p.host || ''}"></label>
        <label>장소<input id="f-place" value="${p.place || ''}"></label>
      </div>

      <fieldset class="picks">
        <legend>누가 함께하나</legend>
        ${radioRow('audience', OPTS.audiences, p.audience)}
      </fieldset>
      <fieldset class="picks">
        <legend>어떤 일인가</legend>
        ${radioRow('track', OPTS.tracks, p.track)}
      </fieldset>
      <fieldset class="picks">
        <legend>나란히 도는가</legend>
        <label class="pick">
          <input type="checkbox" id="f-parallel" ${p.parallel ? 'checked' : ''}>
          <span class="pick-l">나란히 도는 프로그램</span>
          <span class="pick-h">${OPTS.parallel_hint}</span>
        </label>
      </fieldset>

      <p class="warn" id="f-warn" hidden></p>
      <div class="frow end">
        <button class="btn ghost" id="f-cancel" type="button">취소</button>
        <button class="btn" id="f-save" type="button">저장</button>
      </div>
    </div>`;
  box.hidden = false;

  const close = () => { box.hidden = true; box.innerHTML = ''; };
  box.querySelector('#f-cancel').onclick = close;
  box.onclick = e => { if (e.target === box) close(); };
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });

  box.querySelector('#f-save').onclick = async () => {
    const warn = box.querySelector('#f-warn');
    const body = {
      name: box.querySelector('#f-name').value.trim(),
      day: box.querySelector('#f-day').value,
      start_time: box.querySelector('#f-start').value.trim(),
      end_time: box.querySelector('#f-end').value.trim() || null,
      host: box.querySelector('#f-host').value.trim(),
      place: box.querySelector('#f-place').value.trim(),
      audience: box.querySelector('input[name=audience]:checked').value,
      track: box.querySelector('input[name=track]:checked').value,
      parallel: box.querySelector('#f-parallel').checked,
    };
    if (!body.name) { warn.textContent = '이름을 적어주세요.'; warn.hidden = false; return; }
    const url = editing ? `/live/program/${p.id}` : '/live/program';
    const res = await fetch(url, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      warn.textContent = data.detail || '저장하지 못했습니다.';
      warn.hidden = false;
      return;
    }
    location.href = `/live?stay=1&day=${encodeURIComponent(body.day)}`;
  };
}

['addpgm', 'addpgm0'].forEach(id => {
  const b = document.getElementById(id);
  if (b) b.onclick = () => openProgramForm(null);
});

/* 지난 회차에서 프로그램표 가져오기 (5-5) */
const copybtn = document.getElementById('copybtn');
if (copybtn) copybtn.onclick = async () => {
  const src = document.getElementById('copysrc').value;
  const warn = document.getElementById('copywarn');
  copybtn.disabled = true;
  const res = await fetch('/live/copy', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({source_retreat_id: Number(src)}),
  });
  const data = await res.json().catch(() => ({}));
  copybtn.disabled = false;
  if (!res.ok) { warn.textContent = data.detail || '가져오지 못했습니다.'; warn.hidden = false; return; }
  location.reload();
};

if (LIVE.programs && LIVE.programs.length) {
  select(selected == null ? 0 : selected);
  // 넓은 화면에서는 둘 다 보인다. 좁은 화면은 목록부터 — 어디로 갈지 먼저 고른다.
  showDetail(false);
}
})();
