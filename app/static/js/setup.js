/* 새 회차 세팅 마법사 — 시각 스펙 docs/mockups/retreat-setup.html
   날짜 재계산 · 자동 분류 · 명절 충돌 · 구멍 경고는 전부 서버가 계산한다.
   개회일이 바뀌면 /setup/preview 를 다시 불러 화면을 새로 그린다. */
(function () {
'use strict';

const DEPTS = JSON.parse(document.getElementById('setup-departments').textContent);
const COLOR = Object.fromEntries(DEPTS.map(d => [d.key, d.color]));
const NAME = Object.fromEntries(DEPTS.map(d => [d.key, d.name]));


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
    data.items.forEach(item => { if (item.verdict.default_on) sel.add(item.id); });
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
  // 라벨은 쌓인 회차 수에 따라 달라진다. 필터는 실제로 나온 라벨에서 만든다.
  const counts = {}, order = [];
  data.items.forEach(i => {
    const k = i.verdict.label;
    if (!(k in counts)) { counts[k] = 0; order.push(k); }
    counts[k]++;
  });
  $('tools').innerHTML =
    [['all', '전체', data.items.length]].concat(order.map(k => [k, k, counts[k]])).map(([k, label, n]) =>
      `<button data-f="${esc(k)}" aria-pressed="${filt === k}">${esc(label)}
        <span class="n">${n}</span></button>`).join('')
    + `<span class="cnt">이번 회차 선택 <b>${sel.size}</b> / ${data.items.length}건</span>`;
  $('histhead').innerHTML = data.round_labels.map(r => `<span>${esc(r)}</span>`).join('');
  renderBasisNotice();

  $('lib').innerHTML = data.items
    .filter(i => filt === 'all' || i.verdict.label === filt)
    .map(item => {
      const hist = item.history.length
        ? item.history.map(h => `<i class="${h.executed ? '' : 'no'}"><b></b></i>`).join('')
        : data.round_labels.map(() => '<i></i>').join('');
      const dept = item.department_key;
      return `<div class="trow${sel.has(item.id) ? ' on' : ' off'}${item.clash ? ' clash' : ''}"
                   data-i="${esc(item.id)}">
        <span class="box"></span>
        <span class="main"><span class="nm">${esc(item.title)}
          <span class="tag ${item.verdict.tone}">${esc(item.verdict.label)}</span>
          ${item.always_required ? '<span class="tag must">필수 지정</span>' : ''}
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

/* 분류 근거가 몇 회차인지 밝힌다. 3회차가 쌓이면 안내가 저절로 사라진다. */
function renderBasisNotice() {
  let box = $('basisNotice');
  if (!box) {
    box = document.createElement('div');
    box.id = 'basisNotice';
    $('tools').before(box);
  }
  const depth = data.history_depth;
  if (depth >= 3) { box.innerHTML = ''; return; }
  const rounds = data.round_labels.length ? ` (${data.round_labels.map(esc).join(', ')})` : '';
  box.innerHTML = `<div class="alert warn"><span class="ic">근거</span><span>
    자동 분류의 근거는 <b>${depth}회차</b>${rounds}입니다.
    ${depth === 0
      ? '실행 이력이 아직 없어 분류할 수 없습니다. 업무 라이브러리에서 지정한 <b>필수</b>가 구멍 방지를 맡습니다.'
      : '3회차가 쌓이기 전에는 “필수·추천·후순위” 대신 기록만큼만 표현합니다 — ' +
        '한 회차 기록으로 “최근 3회 모두 실행”이라고 말할 수는 없기 때문입니다.'}
    <a href="/library" style="color:inherit;text-decoration:underline">업무 라이브러리에서 필수 지정하기</a></span></div>`;
}

/* ── 4단계: 구멍 방지 경고 ── */
function renderSummary() {
  const chosen = data.items.filter(i => sel.has(i.id));
  const tone = t => chosen.filter(i => i.verdict.tone === t).length;
  const skipped = data.items.length - chosen.length;
  $('sum').innerHTML = `
    <div><b>${chosen.length}</b><span>이번 회차 실행</span></div>
    <div><b>${chosen.filter(i => i.required).length}</b><span>빠뜨리면 안 될 업무</span></div>
    <div><b>${tone('new')}</b><span>신규 제안 채택</span></div>
    <div><b>${skipped}</b><span>미실행으로 기록</span></div>`;

  let html = '';
  // 수동 지정과 자동 판정을 함께 본다 — 이력이 없어도 경고가 작동해야 한다
  const missing = data.items.filter(i => !sel.has(i.id) && i.required);
  if (missing.length) {
    const line = i => `${esc(i.title)} <span style="opacity:.7">(${
      i.always_required ? '총무팀 필수 지정' : esc(i.verdict.basis)})</span>`;
    html += `<div class="alert stop"><span class="ic">경고</span><span>
      <b>빠뜨리면 안 될 업무 ${missing.length}건이 빠졌습니다.</b>
      ${missing.map(line).join(', ')}. 정말 이번에 하지 않는지 확인하세요.</span></div>`;
  }

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
