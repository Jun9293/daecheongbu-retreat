/* 새 회차 세팅 마법사 — 시각 스펙 docs/mockups/retreat-setup.html
   날짜 재계산 · 자동 분류 · 명절 충돌 · 구멍 경고는 전부 서버가 계산한다.
   개회일이 바뀌면 /setup/preview 를 다시 불러 화면을 새로 그린다. */
(function () {
'use strict';

const DEPTS = JSON.parse(document.getElementById('setup-departments').textContent);
const COLOR = Object.fromEntries(DEPTS.map(d => [d.key, d.color]));
const NAME = Object.fromEntries(DEPTS.map(d => [d.key, d.name]));


const off = new Set();          // 제외한 부서
const extraDepts = [];          // 이번 회차에 새로 만든 부서
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
      department_keys: activeKeys(),
    }),
  });
  busy = false;
  if (!res.ok) { alert('계산에 실패했습니다. 개회일을 확인해주세요.'); return; }
  data = await res.json();
  if (!touched) {
    // 팀들이 고른 것이 있으면 그것이 답이다. 없으면 자동 분류의 기본값.
    if (data.draft && data.draft.submitted) {
      data.draft.selected.forEach(id => sel.add(String(id)));
      data.draft.adopted.forEach(t => sel.add('new:' + t));
    } else {
      data.items.forEach(item => { if (item.verdict.default_on) sel.add(item.id); });
    }
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
const allDepts = () => DEPTS.concat(extraDepts);

function renderTeams() {
  $('teams').innerHTML = allDepts().map(d =>
    `<div class="tchip${off.has(d.key) ? ' off' : ''}" data-t="${d.key}">
      <i style="background:${d.color}"></i>${esc(d.name)}
      <span class="x">${off.has(d.key) ? '+' : '×'}</span></div>`).join('');
  $('teams').querySelectorAll('[data-t]').forEach(chip => chip.onclick = () => {
    const key = chip.dataset.t;
    off.has(key) ? off.delete(key) : off.add(key);
    renderTeams();
  });
}

$('addDept').onclick = async () => {
  const name = $('newDeptName').value.trim();
  if (!name) { $('newDeptName').focus(); return; }
  const res = await fetch('/setup/department', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, color: $('newDeptColor').value}),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '부서를 추가하지 못했습니다.'); return; }
  const dept = await res.json();
  extraDepts.push(dept);
  COLOR[dept.key] = dept.color;
  NAME[dept.key] = dept.name;
  $('newDeptName').value = '';
  renderTeams();
};

const activeKeys = () => allDepts().map(d => d.key).filter(k => !off.has(k));

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
  renderDraftPanel();

  const shown = data.items.filter(i => filt === 'all' || i.verdict.label === filt);
  // 성격이 다른 셋으로 나눈다 — 섞어 놓으면 무엇을 고르는지가 흐려진다
  const sections = [
    {key: 'main', title: 'Main 업무',
     hint: '산출물이 남는 단위. 아래 하위 업무가 함께 딸려 옵니다',
     rows: shown.filter(i => i.kind === 'library' && i.task_kind === 'main')},
    {key: 'schedule', title: '일정',
     hint: '논의 없이 날짜만 지키면 되는 별도 업무',
     rows: shown.filter(i => i.kind === 'library' && i.task_kind === 'schedule')},
    {key: 'suggestion', title: 'Claude 제안',
     hint: '이력에 없는 업무. 근거를 함께 확인하세요',
     rows: shown.filter(i => i.kind === 'suggestion')},
  ].filter(sec => sec.rows.length);

  const dept = key => key
    ? `<i style="background:${COLOR[key] || '#69726D'}"></i>${esc(NAME[key] || key)}`
    : '담당 없음';

  const rowHtml = item => {
    const hist = item.history.length
      ? item.history.map(h => `<i class="${h.executed ? '' : 'no'}"><b></b></i>`).join('')
      : data.round_labels.map(() => '<i></i>').join('');
    const on = sel.has(item.id);
    const subs = (item.children || []).map(sub => `
      <div class="subrow${on ? '' : ' off'}">
        <span class="branch">↳</span>
        <span class="nm">${esc(sub.title)}</span>
        <span class="dwlbl">D-${sub.d_week}주</span>
        <span class="dtlbl">${esc(sub.start_label)}</span>
      </div>`).join('');
    return `<div class="tgroup">
      <div class="trow${on ? ' on' : ' off'}${item.clash ? ' clash' : ''}" data-i="${esc(item.id)}">
        <span class="box"></span>
        <span class="main"><span class="nm">${esc(item.title)}
          <span class="tag ${item.verdict.tone}">${esc(item.verdict.label)}</span>
          ${item.always_required ? '<span class="tag must">필수 지정</span>' : ''}
          ${item.sub_count ? `<span class="tag sub">하위 ${item.sub_count}</span>` : ''}</span>
          ${item.rationale ? `<span class="why">${esc(item.rationale)}</span>` : ''}</span>
        <span class="tm">${dept(item.department_key)}</span>
        <span class="hist">${hist}</span>
        <span class="dwlbl">D-${item.d_week}주</span>
        <span class="dtlbl">${esc(item.start_label)}</span>
        ${item.kind === 'library' ? `<button type="button" class="editbtn" data-edit="${esc(item.id)}"
            title="이 업무 편집">편집</button>` : ''}
      </div>${subs}</div>`;
  };

  $('lib').innerHTML = sections.map(sec => {
    let week = null;
    const body = sec.rows.map(item => {
      let divider = '';
      // 진행 순서가 읽히도록 시작 주차가 바뀌는 곳에 눈금을 둔다
      if (sec.key !== 'suggestion' && item.d_week !== week) {
        week = item.d_week;
        divider = `<div class="weekmark"><b>D-${week}주</b><span>${esc(item.start_label)}</span></div>`;
      }
      return divider + rowHtml(item);
    }).join('');
    return `<section class="libsec">
      <h3>${sec.title}<span class="n">${sec.rows.length}</span>
        <em>${sec.hint}</em></h3>${body}</section>`;
  }).join('') || '<div class="libempty">이 분류에 해당하는 업무가 없습니다.</div>';

  $('tools').querySelectorAll('[data-f]').forEach(b => b.onclick = () => { filt = b.dataset.f; renderLib(); });
  $('lib').querySelectorAll('[data-i]').forEach(row => row.onclick = e => {
    if (e.target.closest('[data-edit]')) return;      // 편집 버튼은 선택을 건드리지 않는다
    const id = row.dataset.i;
    sel.has(id) ? sel.delete(id) : sel.add(id);
    renderLib();
  });
  $('lib').querySelectorAll('[data-edit]').forEach(b => b.onclick = e => {
    e.stopPropagation();
    const item = data.items.find(i => i.id === b.dataset.edit);
    if (item) startEdit(item);
  });
  fillEditor();
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

/* 팀별 수집이 진행 중이면 현황을 보여주고, 제출된 선택을 그대로 쓴다. */
function renderDraftPanel() {
  const box = $('draftPanel');
  const d = data.draft;
  if (!d) { box.innerHTML = ''; return; }
  const rows = d.rows.map(r => `<div class="draftrow ${r.state === '제출' ? 'in' : ''}">
      <b>${esc(r.name)}</b>
      <span class="st">${r.state}</span>
      <span class="n">${r.count}건</span>
      ${r.by ? `<span class="by">${esc(r.by)}</span>` : ''}
      ${r.note ? `<span class="note">${esc(r.note)}</span>` : ''}</div>`).join('');
  box.innerHTML = `<div class="alert ${d.all_in ? 'info' : 'warn'}">
      <span class="ic">수집</span><span>
      <b>${esc(d.name)}</b> — ${d.submitted}/${d.total}개 부서 제출.
      ${d.all_in
        ? '모든 팀이 제출했습니다. 아래 목록은 각 팀이 고른 그대로입니다.'
        : '아직 제출하지 않은 팀이 있습니다. 지금 만들면 그 팀의 업무는 빠집니다.'}
      </span></div>
    <div class="drafttable">${rows}</div>`;
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

  // 선행이 이번 목록에 없으면 그 업무는 시작할 수 없다. 링크를 만들지 않고 알리기만 한다.
  const unmet = [];
  chosen.forEach(i => (i.prereqs || []).forEach(p => {
    if (!sel.has(p.owner_id)) unmet.push(p);
  }));
  if (unmet.length) html += `<div class="alert stop"><span class="ic">경고</span><span>
    <b>선행 업무 ${unmet.length}건이 이번 회차에서 빠졌습니다.</b>
    ${unmet.map(p => `${esc(p.title)} 의 선행 업무 <b>${esc(p.prerequisite_title)}</b>`).join(', ')}
    — 선행이 없으면 그 업무는 시작할 수 없습니다.</span></div>`;

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

/* ── 3단계: 라이브러리 업무 추가·편집 ── */
let editing = null;

function slotOptions() {
  return (data ? data.slots : []).map(s =>
    `<option value="${s.start}" data-end="${s.end}">${esc(s.label)}</option>`).join('');
}

function fillEditor() {
  $('tDept').innerHTML = allDepts()
    .map(d => `<option value="${d.key}">${esc(d.name)}</option>`).join('');
  const opts = slotOptions();
  const keepStart = $('tStart').value, keepEnd = $('tEnd').value;
  $('tStart').innerHTML = opts;
  $('tEnd').innerHTML = (data ? data.slots : []).map(s =>
    `<option value="${s.end}" data-start="${s.start}">${esc(s.label)}</option>`).join('');
  if (keepStart) {
    $('tStart').value = keepStart;
    $('tEnd').value = keepEnd || keepStart;
  } else if (data && data.slots.length) {
    // 처음 열 때는 D-13주에 맞춘다 — 보드가 기본으로 보여주는 시작점.
    // (채운 뒤의 value 를 보면 첫 옵션이 이미 잡혀 있어 늘 참이 된다)
    const i = Math.max(0, data.slots.findIndex(s => s.label.indexOf('D-13주') === 0));
    $('tStart').selectedIndex = i;
    $('tEnd').selectedIndex = i;
  }
  paintParentPicker();
}

/* 상위 업무는 가나다순, 이름으로 좁혀 찾는다 */
function parentPool() {
  return (data ? data.items : [])
    .filter(i => i.kind === 'library' && i.task_kind === 'main')
    .slice().sort((a, b) => a.title.localeCompare(b.title, 'ko'));
}
function paintParentPicker() {
  const pool = parentPool();
  const q = $('tParentSearch').value.trim().toLowerCase();
  const keep = $('tParent').value;
  const rows = pool.filter(i => !q || i.title.toLowerCase().includes(q));
  $('tParent').innerHTML = rows.map(i => `<option value="${esc(i.id)}">${esc(i.title)}</option>`).join('');
  if (rows.some(i => i.id === keep)) $('tParent').value = keep;
  else if (rows.length) $('tParent').selectedIndex = 0;
  $('tParentCount').textContent = q ? `${rows.length}건 / 전체 ${pool.length}건` : `전체 ${pool.length}건`;
}

function startEdit(item) {
  editing = item;
  $('editorTitle').innerHTML = `업무 편집 <span class="n">${esc(item.title)}</span>`;
  $('tTitle').value = item.title;
  $('tDept').value = item.department_key || allDepts()[0].key;
  $('tKind').value = item.task_kind || 'main';
  const startSlot = (data.slots || []).find(s => s.start <= item.start && item.start <= s.end);
  if (startSlot) { $('tStart').value = startSlot.start; $('tEnd').value = startSlot.end; }
  $('tParentField').hidden = $('tKind').value !== 'sub';
  $('tSave').textContent = '수정 저장';
  $('tCancel').hidden = false;
  $('taskEditor').scrollIntoView({block: 'nearest'});
  $('tTitle').focus();
}

function resetEditor() {
  editing = null;
  $('editorTitle').innerHTML = '업무 추가 <span class="n">라이브러리에 새로 만듭니다</span>';
  $('tTitle').value = '';
  $('tSave').textContent = '업무 추가';
  $('tCancel').hidden = true;
  $('tParentField').hidden = true;
}

$('tKind').onchange = () => {
  $('tParentField').hidden = $('tKind').value !== 'sub';
  if (!$('tParentField').hidden) paintParentPicker();
};
$('tParentSearch').oninput = paintParentPicker;
$('tStart').onchange = () => {
  if ($('tEnd').value < $('tStart').value) $('tEnd').selectedIndex = $('tStart').selectedIndex;
};
$('tEnd').onchange = () => {
  if ($('tEnd').value < $('tStart').value) $('tStart').selectedIndex = $('tEnd').selectedIndex;
};
$('tCancel').onclick = resetEditor;

$('tSave').onclick = async () => {
  const title = $('tTitle').value.trim();
  if (!title) { $('tTitle').focus(); return; }
  const kind = $('tKind').value;
  if (kind === 'sub' && !$('tParent').value) { alert('상위 업무를 골라주세요.'); return; }
  if ($('tEnd').value < $('tStart').value) { alert('마감이 시작보다 빠릅니다.'); return; }
  const body = {
    title,
    department_key: $('tDept').value,
    kind,
    open_date: $('op').value,
    start: $('tStart').value,
    end: $('tEnd').value,
    parent_library_id: kind === 'sub' ? Number($('tParent').value) : null,
  };
  const url = editing ? `/library/${editing.id}/edit` : '/library/new';
  const res = await fetch(url, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '저장하지 못했습니다.'); return; }
  const saved = await res.json();
  resetEditor();
  const keep = new Set(sel);
  await reload();
  sel.clear();
  keep.forEach(id => sel.add(id));
  if (!editing) sel.add(String(saved.library_id));   // 새로 만든 것은 켜 둔다
  renderLib();
};

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
  $('askTeams').hidden = !(n === 2 && !(data && data.draft));
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
      department_keys: activeKeys(),
      new_departments: extraDepts,
      selected: chosen.filter(i => i.kind === 'library').map(i => Number(i.id)),
      adopted: chosen.filter(i => i.kind === 'suggestion').map(i => i.title),
    }),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '회차를 만들지 못했습니다.'); return; }
  const out = await res.json();
  location.href = out.redirect;
};

$('askTeams').onclick = async () => {
  if (!confirm('각 팀에 업무 선택을 요청합니다. 팀이 제출한 내용이 3단계에 반영됩니다.')) return;
  const res = await fetch('/setup/draft', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name: $('nm').value,
      open_date: $('op').value,
      close_date: $('cl').value,
      meal_subsidy: Number($('subsidy').value) || 0,
      department_keys: activeKeys(),
      new_departments: extraDepts,
    }),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '요청하지 못했습니다.'); return; }
  location.href = (await res.json()).redirect;
};

['op', 'cl'].forEach(id => $(id).onchange = reload);
renderTeams();
go(1);
reload();
})();
