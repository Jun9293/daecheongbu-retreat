/* 새 회차 세팅 마법사 — 시각 스펙 docs/mockups/retreat-setup.html
   날짜 재계산 · 자동 분류 · 명절 충돌 · 구멍 경고는 전부 서버가 계산한다.
   개회일이 바뀌면 /setup/preview 를 다시 불러 화면을 새로 그린다. */
(function () {
'use strict';

const DEPTS = JSON.parse(document.getElementById('setup-departments').textContent);
const COLOR = Object.fromEntries(DEPTS.map(d => [d.key, d.color]));
const NAME = Object.fromEntries(DEPTS.map(d => [d.key, d.name]));
const TAG = {'필수': 'must', '추천': 'rec', '후순위': 'low', 'Claude 제안': 'new'};

const off = new Set();          // 제외한 부서
const sel = new Set();          // 선택한 업무 (id 문자열)
let data = null, filt = 'all', step = 1, touched = false, busy = false;

const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s)
  .replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

/* ── 서버에서 다시 계산 ── */
async function reload() {
  busy = true;
  const res = await fetch('/setup/preview', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      open_date: $('op').value,
      close_date: $('cl').value,
      department_keys: DEPTS.map(d => d.key).filter(k => !off.has(k)),
    }),
  });
  busy = false;
  if (!res.ok) { alert('계산에 실패했습니다. 개회일을 확인해주세요.'); return; }
  data = await res.json();
  if (!touched) {              // 첫 계산에서만 기본 선택을 잡는다
    data.items.forEach(item => { if (item.classification !== '후순위') sel.add(item.id); });
    touched = true;
  }
  renderWeeks();
  if (step === 3) renderLib();
  if (step === 4) renderSummary();
}

/* ── 1단계 ── */
function renderWeeks() {
  if (!data) return;
  $('wk').innerHTML = data.weeks.map(w =>
    `<div class="${w.holiday ? 'clash' : ''}"><b>D-${w.d_week}주</b><span>${w.label}</span>
      ${w.holiday ? `<i>${esc(w.holiday)} 주간</i>` : ''}</div>`).join('')
    + `<div class="day"><b>개회</b><span>${fmt($('op').value)}</span></div>`;
  $('clashBox').innerHTML = data.clashes.length
    ? `<div class="alert warn"><span class="ic">확인</span><span>
        <b>${data.clashes.map(c => `D-${c.d_week}주(${c.label}) ${esc(c.name)}`).join(' · ')}</b> 주간과 겹칩니다.
        논의와 검토가 주말에 이뤄지는데 그 주말이 교회 일정으로 막힙니다.
        해당 주 업무를 앞당기는 것을 검토하세요.</span></div>`
    : '';
}
function fmt(iso) {
  if (!iso) return '';
  const [, m, d] = iso.split('-');
  return `${Number(m)}/${Number(d)}`;
}

/* ── 2단계 ── */
function renderTeams() {
  $('teams').innerHTML = DEPTS.map(d =>
    `<div class="tchip${off.has(d.key) ? ' off' : ''}" data-t="${d.key}">
      <i style="background:${d.color}"></i>${esc(d.name)}
      <span class="x">${off.has(d.key) ? '+' : '×'}</span></div>`).join('');
  $('teams').querySelectorAll('[data-t]').forEach(chip => chip.onclick = () => {
    const key = chip.dataset.t;
    off.has(key) ? off.delete(key) : off.add(key);
    renderTeams();
  });
}

/* ── 3단계 ── */
function renderLib() {
  const counts = {all: data.items.length, '필수': 0, '추천': 0, '후순위': 0, 'Claude 제안': 0};
  data.items.forEach(i => counts[i.classification]++);
  $('tools').innerHTML =
    ['all', '필수', '추천', '후순위', 'Claude 제안'].map(k =>
      `<button data-f="${k}" aria-pressed="${filt === k}">${k === 'all' ? '전체' : k}
        <span class="n">${counts[k]}</span></button>`).join('')
    + `<span class="cnt">이번 회차 선택 <b>${sel.size}</b> / ${data.items.length}건</span>`;
  $('histhead').innerHTML = data.round_labels.map(r => `<span>${esc(r)}</span>`).join('');

  $('lib').innerHTML = data.items
    .filter(i => filt === 'all' || i.classification === filt)
    .map(item => {
      const hist = item.history.length
        ? item.history.map(h => `<i class="${h.executed ? '' : 'no'}"><b></b></i>`).join('')
        : data.round_labels.map(() => '<i></i>').join('');
      const dept = item.department_key;
      return `<div class="trow${sel.has(item.id) ? ' on' : ' off'}${item.clash ? ' clash' : ''}"
                   data-i="${esc(item.id)}">
        <span class="box"></span>
        <span class="main"><span class="nm">${esc(item.title)}
          <span class="tag ${TAG[item.classification]}">${item.classification}</span>
          ${item.sub_count ? `<span class="tag low">하위 ${item.sub_count}</span>` : ''}</span>
          ${item.rationale ? `<span class="why">${esc(item.rationale)}</span>` : ''}</span>
        <span class="tm">${dept ? `<i style="background:${COLOR[dept] || '#69726D'}"></i>${esc(NAME[dept] || dept)}` : '담당 없음'}</span>
        <span class="hist">${hist}</span>
        <span class="dwlbl">D-${item.d_week}주</span><span class="dtlbl">${esc(item.start_label)}</span></div>`;
    }).join('');

  $('tools').querySelectorAll('[data-f]').forEach(b => b.onclick = () => { filt = b.dataset.f; renderLib(); });
  $('lib').querySelectorAll('[data-i]').forEach(row => row.onclick = () => {
    const id = row.dataset.i;
    sel.has(id) ? sel.delete(id) : sel.add(id);
    renderLib();
  });
}

/* ── 4단계: 구멍 방지 경고 ── */
function renderSummary() {
  const chosen = data.items.filter(i => sel.has(i.id));
  const count = k => chosen.filter(i => i.classification === k).length;
  const skipped = data.items.length - chosen.length;
  $('sum').innerHTML = `
    <div><b>${chosen.length}</b><span>이번 회차 실행</span></div>
    <div><b>${count('필수')}</b><span>필수</span></div>
    <div><b>${count('추천')}</b><span>추천</span></div>
    <div><b>${count('Claude 제안')}</b><span>신규 제안 채택</span></div>
    <div><b>${skipped}</b><span>미실행으로 기록</span></div>`;

  let html = '';
  const missing = data.items.filter(i => !sel.has(i.id) && i.classification === '필수');
  if (missing.length) html += `<div class="alert stop"><span class="ic">경고</span><span>
    <b>필수 업무 ${missing.length}건이 빠졌습니다.</b> 최근 3회차 모두 실행된 업무입니다 —
    ${missing.map(i => esc(i.title)).join(', ')}. 정말 이번에 하지 않는지 확인하세요.</span></div>`;

  const orphan = chosen.filter(i => i.department_key && off.has(i.department_key));
  if (orphan.length) html += `<div class="alert stop"><span class="ic">경고</span><span>
    제외한 부서가 맡던 업무 <b>${orphan.length}건</b>에 담당이 없습니다 —
    ${orphan.map(i => esc(i.title)).join(', ')}.</span></div>`;

  const clashing = chosen.filter(i => i.clash);
  if (clashing.length) html += `<div class="alert warn"><span class="ic">확인</span><span>
    명절 주간에 <b>${clashing.length}건</b>이 배정됩니다 — ${clashing.map(i => esc(i.title)).join(', ')}.</span></div>`;

  html += `<div class="alert info"><span class="ic">기록</span><span>
    이번에 선택하지 않은 <b>${skipped}건</b>은 삭제되지 않고 <b>미실행</b>으로 기록됩니다.
    이 기록이 쌓여 다음 회차의 필수·추천·후순위 분류에 반영됩니다.</span></div>`;
  $('warns').innerHTML = html;
}

/* ── 단계 이동 ── */
const HINTS = {
  1: '개회일을 바꾸면 모든 업무 날짜가 함께 이동합니다.',
  2: '부서를 눌러 제외하거나 되돌릴 수 있습니다.',
  3: '분류는 실행 이력에서 자동 계산됩니다 — 최근 3회 모두 실행하면 필수, 3회 모두 없으면 후순위.',
  4: '생성 후에도 언제든 수정할 수 있습니다.',
};
function go(n) {
  step = n;
  document.querySelectorAll('.wiz .pane').forEach((p, i) => p.classList.toggle('on', i + 1 === n));
  document.querySelectorAll('.steps div').forEach((d, i) => {
    d.classList.toggle('on', i + 1 === n);
    d.classList.toggle('past', i + 1 < n);
  });
  $('prev').disabled = n === 1;
  $('next').textContent = n === 4 ? '회차 만들기' : '다음';
  $('hint').textContent = HINTS[n];
  if (n === 3) renderLib();
  if (n === 4) renderSummary();
  document.querySelector('main.wiz').scrollTop = 0;
}

$('prev').onclick = () => go(Math.max(1, step - 1));
$('next').onclick = async () => {
  if (step < 4) { go(step + 1); return; }
  if (busy) return;
  const chosen = data.items.filter(i => sel.has(i.id));
  const res = await fetch('/setup/create', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name: $('nm').value,
      open_date: $('op').value,
      close_date: $('cl').value,
      meal_subsidy: Number($('subsidy').value) || 0,
      department_keys: DEPTS.map(d => d.key).filter(k => !off.has(k)),
      selected: chosen.filter(i => i.kind === 'library').map(i => Number(i.id)),
      adopted: chosen.filter(i => i.kind === 'suggestion').map(i => i.title),
    }),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '회차를 만들지 못했습니다.'); return; }
  const out = await res.json();
  location.href = out.redirect;
};

['op', 'cl'].forEach(id => $(id).onchange = reload);
renderTeams();
go(1);
reload();
})();
