/* 업무 상세 패널 — **보드와 달력이 같이 쓰는 한 벌** (CLAUDE.md 4-9 · 4-13).
 *
 * 달력의 점을 눌렀을 때 `/board?task=` 로 넘겨 보내던 것을 그만두면서 여기로
 * 뺐습니다. 보던 달을 잃지 않으려면 달력에서도 패널이 열려야 하는데, 그렇다고
 * 패널을 한 벌 더 만들면 논의·상태·첨부·선후행이 두 곳에서 갈리고
 * **갈린 쪽을 아무도 눈치채지 못합니다.**
 *
 * 그래서 화면(templates/partials/drawer.html)도 코드(이 파일)도 한 벌입니다.
 * 보드와 달력은 "내 화면은 이렇게 고쳐 그린다" 만 알려 줍니다:
 *
 *     Drawer.init({
 *       meta(runId), onOpen, onClose, onStatus, onDates, onAssignee,
 *       onDepartment, link, goTo, canGoTo, isTaskClick, afterLayout,
 *       openFromUrl,
 *       __unused: {이름: '왜 안 쓰는가'},
 *       __unusedFor: '<이 계약의 도장>',
 *     });
 *
 * 여기에 무언가 더할 때 **어느 한 화면만 생각하면 안 됩니다** —
 * 달력에는 바가 없고 보드에는 점이 없습니다.
 *
 * **안 쓰는 것은 `__unused` 에 이유와 함께 적습니다.** `call()` 은 없는
 * 핸들러를 조용히 건너뛰므로, 적어 두지 않으면 "일부러 안 쓴 것" 과
 * "넘기는 걸 빠뜨린 것" 이 화면에서 똑같이 생겼습니다 — 실제로 달력의
 * `onDates` 를 빠뜨려서, 패널은 새 날짜를 말하는데 점은 옛 칸에 남아
 * 있었습니다. `tests/test_calendar.py` 가 이 목록과 실제 등록을 대조합니다.
 *
 * **그런데 목록은 등록과 맞아도 이유가 낡습니다.** 두 번 그랬습니다 —
 * `onOpen`("달력이 따로 할 일이 없다")과 `onAssignee`("그대로 둔다")가
 * 둘 다 **이 파일이 새 일을 시작한 그 커밋에서** 거짓이 됐는데 목록은
 * 그대로였습니다. 낡음은 아무 때나 생기지 않고 **계약이 바뀌는 순간**에
 * 생깁니다.
 *
 * 그래서 위 머리말과 `call()` 이름 목록만 해시로 떠서 각 화면이
 * `__unusedFor` 에 **도장**으로 들고 있습니다. 계약이 바뀌면 도장이 안 맞아
 * 빨개지고, 그때 `__unused` 를 처음부터 다시 읽습니다.
 * 파일 전체가 아니라 계약만 뜨는 이유는, 무관한 수정에 걸리면 사람이
 * 읽지 않고 도장만 찍게 되기 때문입니다.
 */
(function () {
'use strict';

const STATUS = {
  '대기':   {label: '예정',   color: '#4A544F'},
  '진행중': {label: '진행중', color: '#1668E3'},
  '완료':   {label: '완료',   color: '#8B948F'},
  '지연':   {label: '지연',   color: '#C8442E'},
};
const WD = ['일', '월', '화', '수', '목', '금', '토'];

const $ = id => document.getElementById(id);
const dw = $('drawer');
if (!dw) return;                       // 패널이 없는 화면에서는 아무것도 하지 않는다

const md = iso => iso ? iso.slice(5).replace('-', '/') : '';

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
}

let cur = null, detail = null, dragEnd = 0;

/* 화면마다 다른 것만 host 가 맡는다. 없으면 아무것도 하지 않는다 —
   달력에는 바가 없고 보드에는 점이 없으므로 대부분이 선택이다. */
let host = {};
const call = (name, ...args) =>
  (typeof host[name] === 'function') ? host[name](...args) : undefined;

/* ── 열고 닫기 ── */
async function openDrawer(runId) {
  cur = runId;
  const m = call('meta', runId) || {};
  selectTab('rules');   // 열면 업무 규칙이 먼저 (CLAUDE.md 4-9)
  $('dtitle').textContent = m.title || '';
  $('dlog').innerHTML = '<div class="empty">불러오는 중…</div>';
  dw.classList.add('open');
  dw.setAttribute('aria-hidden', 'false');
  document.body.classList.add('dopen');
  call('onOpen', runId);
  setTimeout(() => call('afterLayout'), 240);

  const res = await fetch(`/board/task/${runId}`, {headers: {'Accept': 'application/json'}});
  if (!res.ok) { $('dlog').innerHTML = '<div class="empty">불러오지 못했습니다.</div>'; return; }
  const data = await res.json();
  if (String(cur) !== String(runId)) return;
  detail = data;
  renderDrawer();
}

function closeDrawer() {
  dw.classList.remove('open');
  dw.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('dopen');
  cur = null; detail = null;
  cancelUpload({quiet: true});
  call('onClose');
}

function selectTab(name) {
  document.querySelectorAll('#dtabs button').forEach(x =>
    x.setAttribute('aria-selected', x.dataset.p === name));
  document.querySelectorAll('#drawer .pane').forEach(p =>
    p.classList.toggle('on', p.id === 'p-' + name));
}

$('dclose').onclick = closeDrawer;
$('dtabs').onclick = e => {
  const b = e.target.closest('button');
  if (b) selectTab(b.dataset.p);
};
addEventListener('keydown', e => { if (e.key === 'Escape') { closeMenus(); closeDrawer(); } });

/* ── 본문 ── */
function renderDrawer() {
  const d = detail;
  const st = STATUS[d.status] || STATUS['대기'];
  $('dkick').innerHTML =
    `<span class="chip solid" style="--team:${esc(d.department_color)}">${esc(d.department)}</span>
     <span class="chip">${d.kind_label}</span>
     <button class="chip stat" id="statchip" ${d.can_edit ? '' : 'disabled'}>
       <span class="cv" style="background:${esc(st.color)}"></span>${esc(st.label)}${d.can_edit ? ' ▾' : ''}</button>`;
  if (d.can_edit) {
    $('statchip').onclick = e => { e.stopPropagation(); statMenu(e.currentTarget); };
  }
  $('dtitle').textContent = d.title;
  const teams = (d.departments || []).map(t =>
    `<option value="${esc(t.key)}" data-color="${esc(t.color)}" ${t.key === d.department_key ? 'selected' : ''}>${esc(t.name)}</option>`).join('');
  const people = (d.candidates || []).map(p =>
    `<option value="${p.id}" ${p.id === d.assignee_id ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
  $('dmeta').innerHTML =
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
        ? `<span class="pill person"><i class="dot" id="ddeptdot" style="background:${esc(d.department_color)}"></i>
             <select id="ddept"><option value="">담당 없음</option>${teams}</select></span>`
        : `<span class="pill flat person"><i class="dot" style="background:${esc(d.department_color)}"></i>${esc(d.department)}</span>`}</dd>
     <dt>담당자</dt><dd>${d.can_edit
        ? `<span class="pill person"><select id="dassignee"><option value="">지정 안 함</option>${people}</select></span>`
        : `<span class="pill flat person">${esc(d.assignee || '지정 안 함')}</span>`}</dd>
     <dt>상위</dt><dd>${d.parent_title ? esc(d.parent_title) : '—'}</dd>
     <dt>관련팀</dt><dd>${d.related_departments.map(esc).join(', ') || '—'}</dd>`;

  if (d.can_edit) {
    const start = $('dstart'), end = $('dend');
    const saveDates = async () => {
      if (!start.value) return;
      if (end.value && end.value < start.value) { end.value = start.value; }
      const res = await fetch(`/board/task/${d.run_id}/dates`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({start: start.value, end: end.value || start.value}),
      });
      if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '기간을 바꾸지 못했습니다.'); return; }
      const saved = await res.json();
      const span = $('dspan');
      if (span) span.textContent = spanLabel(saved.start, saved.end);
      detail.start = saved.start;
      detail.end = saved.end;
      call('onDates', d.run_id, saved);
    };
    start.onchange = saveDates;
    end.onchange = saveDates;

    // 날짜 칸을 누르면 달력이 열린다 (아이콘 없이)
    [start, end].forEach(input => {
      input.onclick = () => { try { input.showPicker(); } catch (err) { /* 지원 안 하면 기본 동작 */ } };
    });

    $('ddept').onchange = async e => {
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
      // 업무가 다른 부서의 줄로 옮겨간다 — 화면을 다시 그려야 한다.
      // **직접 고쳐 그렸다고 `true` 를 돌려준 화면만** 새로고침을 건너뛴다.
      // `undefined` 로 갈랐더니, 핸들러가 있어도 반환값을 빠뜨리면 핸들러가
      // 돈 **뒤에** 페이지가 통째로 새로고침됐다 — 두 번 일하고 화면도 잃는다.
      if (call('onDepartment', d.run_id) !== true) location.reload();
    };

    $('dassignee').onchange = async e => {
      const value = e.target.value;
      const res = await fetch(`/board/task/${d.run_id}/assignee`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: value ? Number(value) : null}),
      });
      if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '지정하지 못했습니다.'); return; }
      const saved = await res.json();
      detail.assignee_id = saved.assignee_id;
      detail.assignee = saved.assignee;
      // 이름만이 아니라 **응답 전부**를 넘긴다 — 달력은 서버가 만든
      // 툴팁 문장이 필요하고, 보드는 지금처럼 이름만 쓴다.
      call('onAssignee', d.run_id, saved.assignee, saved);
    };
  }

  renderLog();
  renderRules();

  let note = '';
  if (d.suggestion_rationale) note += `<div class="note"><b>CLAUDE 제안 근거</b>${esc(d.suggestion_rationale)}</div>`;
  if (d.reclassification_note) note += `<div class="note"><b>분류·담당 변경 기록</b>${esc(d.reclassification_note)}</div>`;
  $('dnote').innerHTML = note;
  $('daddlog').hidden = !d.can_edit;

  renderRel(d);
  renderFiles(d);
  renderDiag(d);
  calendar(d);
}

/* 며칠짜리인지 한눈에 — 날짜만 보고 세지 않게 */
function spanLabel(start, end) {
  if (!start) return '';
  const a = new Date(start), b = new Date(end || start);
  const days = Math.round((b - a) / 864e5) + 1;
  return days > 1 ? days + '일' : '하루';
}

/* ── 연결된 업무: 선행 / 후속 / 관련 ────────────────────────────────
   셋을 한 덩어리로 그리면 무엇이 나를 막는지 읽히지 않는다.
   선행은 방향이 있고 '기다리는 쪽'에만 저장한다. 후속은 그 역방향을
   서버가 계산한 것이라 여기서 직접 고치지 않는다 — 고치려면 그쪽 업무를
   열어야 한다. 관계는 회차가 아니라 라이브러리에 붙으므로 다음 회차에도 간다. */
function relItem(r) {
  // '이동' 은 보드에만 뜻이 있다. 달력에는 스크롤해서 갈 자리가 없으므로
  // 메뉴에 내지 않는다 — 눌러도 아무 일이 없는 항목을 보여줄 이유가 없다.
  const move = host.canGoTo
    ? '<button data-act="move">이동<span class="mi">보드</span></button>' : '';
  return `<div class="relitem">
    <button class="rb" data-rel="${r.run_id}">
      <span class="dot" style="background:${esc(r.color)}"></span>${esc(r.title)}
      <span class="rl">${r.kind_label} · ${esc(r.department)}</span></button>
    <div class="menu">
      <button data-act="open">열기<span class="mi">상세</span></button>
      ${move}</div></div>`;
}

function renderRel(d) {
  const pre = d.prerequisites || [], dep = d.dependents || [], rel = d.related || [];
  $('relN').textContent = (pre.length + dep.length + rel.length) || '';

  const section = (title, rows, hint, edit) => `<div class="relsec">
    <h4>${title}<span class="n">${rows.length}</span>${
      edit ? '<button class="edit" id="preedit">고치기</button>' : ''}</h4>
    ${rows.length ? rows.map(relItem).join('')
      : `<div class="relnone">${hint}</div>`}</div>`;

  $('drel').innerHTML =
    section('선행 — 끝나야 시작할 수 있다', pre, '기다리는 업무 없음', d.can_edit) +
    section('후속 — 나를 기다린다', dep, '나를 기다리는 업무 없음', false) +
    section('관련 — 방향 없음', rel, '연결된 업무 없음', false) +
    `<div class="relnote">선후행은 회차가 아니라 <b>업무 자체</b>에 붙습니다 —
      업무 규칙과 같이 <b>다음 회차에도 그대로 적용됩니다.</b>
      후속은 저장하지 않고 선행의 역방향으로 계산합니다.</div>`;

  const edit = $('preedit');
  if (edit) edit.onclick = () => openPrereqPicker(d);
}

/* 선행 고르기 — 이 업무가 기다릴 업무를 고른다 */
function openPrereqPicker(d) {
  const chosen = new Set((d.prerequisites || []).map(r => r.run_id));
  const box = $('prepick');
  box.innerHTML = `<div class="sheetbox">
    <div class="sh"><b>${esc(d.title)} 이(가) 기다릴 업무</b>
      <button type="button" class="btn sm" data-close="1">닫기</button></div>
    <p class="sechint" id="prepickwarn" hidden></p>
    <input type="search" class="find" id="prepickfind" placeholder="이름으로 좁혀 찾기" autocomplete="off">
    <div class="plist" id="prepicklist">${(d.link_candidates || []).map(c =>
      `<label data-name="${esc(c.title)}">
        <input type="checkbox" value="${esc(c.run_id)}" ${chosen.has(c.run_id) ? 'checked' : ''}>
        <span>${esc(c.title)}</span><span class="dw">D-${c.d_week}주</span></label>`).join('')}</div>
    <div class="sh end">
      <button type="button" class="btn pri" id="prepicksave">저장</button>
      <button type="button" class="btn" data-close="1">취소</button></div></div>`;
  box.hidden = false;

  $('prepickfind').oninput = e => {
    const q = e.target.value.trim().toLowerCase();
    box.querySelectorAll('#prepicklist label').forEach(el => {
      el.hidden = q ? !el.dataset.name.toLowerCase().includes(q) : false;
    });
  };
  box.onclick = e => {
    if (e.target === box || e.target.closest('[data-close]')) box.hidden = true;
  };
  $('prepicksave').onclick = async () => {
    const ids = [...box.querySelectorAll('#prepicklist input:checked')].map(i => Number(i.value));
    const res = await fetch(`/board/task/${cur}/prerequisites`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({run_ids: ids}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const warn = $('prepickwarn');
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

/* ── 첨부파일과 링크 (CLAUDE.md 4-9) ────────────────────────────────
   회차별이다. 새 회차를 열면 업무는 따라와도 파일은 따라오지 않는다 —
   논의 내역과 같은 취급이고, 업무 규칙(라이브러리)과 다르다.

   **파일과 링크를 한 목록에 섞는다.** 나누면 "저건 어디 있더라" 를 두 번
   찾게 되는데, 담당자에게 둘은 그냥 자료다. 다만 링크는 우리 서버에 없어서
   지워지거나 권한이 막히면 안 열리고 그건 우리가 어쩔 수 없으므로,
   **점선 테두리와 ↗ 로 그 차이가 눈에 보이게** 한다. */
function fileItem(f) {
  const icon = f.is_link ? '↗' : esc(f.ext || '?');
  const menu = f.is_link
    ? '<button data-fact="open">링크 열기</button>'
    : '<button data-fact="download">내려받기</button>';
  return `<div class="fitem${f.is_link ? ' link' : ''}" data-file="${f.id}">
    <span class="ext">${icon}</span>
    <span class="mid">
      <span class="fname">${esc(f.name)}</span>
      <span class="fmeta">${esc(f.size_label)}${f.by ? ' · <span class="by">' + esc(f.by) + '</span>' : ''} · ${esc(f.at)}</span>
    </span>
    <button class="more" type="button" data-fmenu="${f.id}" aria-label="메뉴">⋯</button>
    <div class="menu">
      ${menu}
      ${f.can_edit ? '<button data-fact="rename">이름 변경</button>' +
                    '<button data-fact="delete">삭제</button>' : ''}
    </div></div>`;
}

function renderFiles(d) {
  const list = $('dfiles');
  const files = d.attachments || [];
  $('fileN').textContent = files.length || '';
  list.innerHTML = files.length
    ? files.map(fileItem).join('')
    : '<div class="fempty">아직 올린 파일이 없습니다.</div>';

  const can = !!d.can_edit;
  $('ddrop').hidden = !can;
  $('dorlink').hidden = !can;
  $('dlinkbtn').hidden = !can;
  if (!can) $('dlinkform').hidden = true;

  const limits = d.attachment_limits || {};
  const limit = $('ddroplimit');
  if (limit) limit.textContent = limits.max_label
    ? `${limits.max_label} 까지 · ${(limits.exts || []).length}가지 형식`
    : '';
  // 안내 문구가 상한과 **같은 숫자**를 말하게 한다. 글에 숫자를 박아 두면
  // 상한을 바꿨을 때 화면이 조용히 거짓말을 한다.
  const tip = $('dfilenote');
  if (tip && limits.tunnel_max_label) {
    tip.innerHTML = '이번 회차에만 남습니다. 다음 회차에는 따라가지 않습니다.<br>'
      + `<b>${esc(limits.tunnel_max_label)}</b> 를 넘는 것은 바깥에서 <b>올릴 때만</b> 실패합니다 — `
      + '영상처럼 큰 것은 링크로 붙이세요.<br>'
      // 올리기와 내려받기는 제한이 다르다. 이 한 줄이 없으면 "큰 파일은 아예
      // 못 쓴다" 로 읽혀서, 집 안에서 올려 두면 되는 길을 아무도 안 쓴다.
      + '<b>내려받기에는 제한이 없습니다.</b> 큰 것은 서버가 있는 곳에서 올려 두면 '
      + '바깥에서 받는 것은 됩니다.';
  }
  $('ddropwarn').hidden = true;
}

function fileWarn(text) {
  const box = $('ddropwarn');
  box.textContent = text;
  box.hidden = !text;
}

/* 서버가 돌려준 목록으로 화면을 다시 그린다. 개수도 함께 움직인다. */
function applyFiles(data) {
  if (!detail) return;
  detail.attachments = data.files || [];
  renderFiles(detail);
}

/* ── 링크 붙이기 ──────────────────────────────────────────────────── */
function linkFormOpen(open) {
  $('dlinkform').hidden = !open;
  $('dlinkbtn').hidden = open || !(detail && detail.can_edit);
  $('dorlink').hidden = open || !(detail && detail.can_edit);
  if (open) {
    linkError('dlinkurlerr', '');
    linkError('dlinknameerr', '');
    $('dlinkurl').focus();
  }
}

/* 틀린 이유는 **붙는 자리 바로 아래**에 적는다. 위나 아래 멀리 적으면
   어느 칸이 틀렸는지 알 수 없어 사람이 둘 다 지우고 다시 쓴다. */
function linkError(id, text) {
  const box = $(id);
  box.textContent = text;
  box.hidden = !text;
  const input = box.previousElementSibling;
  if (input && input.tagName === 'INPUT') input.classList.toggle('bad', !!text);
}

const URL_RE = /^https?:\/\/[^\s]+$/i;
const NOT_A_URL = '주소가 아닙니다. https:// 로 시작하는 주소를 넣어주세요.';
const NEEDS_NAME = '무엇인지 적어주세요. 주소만 있으면 나중에 아무도 열지 않습니다.';

$('dlinkbtn').onclick = () => linkFormOpen(true);
$('dlinkcancel').onclick = () => {
  $('dlinkurl').value = '';
  $('dlinkname').value = '';
  linkFormOpen(false);
};
$('dlinksave').onclick = async () => {
  const url = $('dlinkurl').value.trim();
  const name = $('dlinkname').value.trim();
  // **화면에서도 먼저 본다.** 서버까지 갔다 오지 않아도 알 수 있는 것이고,
  // 어느 칸이 틀렸는지 그 자리에서 말해 주는 편이 빠르다.
  linkError('dlinkurlerr', URL_RE.test(url) ? '' : NOT_A_URL);
  linkError('dlinknameerr', name ? '' : NEEDS_NAME);
  if (!URL_RE.test(url) || !name) return;

  const res = await fetch(`/board/task/${cur}/links`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url, name}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { linkError('dlinkurlerr', data.detail || '붙이지 못했습니다.'); return; }
  $('dlinkurl').value = '';
  $('dlinkname').value = '';
  linkFormOpen(false);
  applyFiles(data);
};

/* ── 올리는 중 ──────────────────────────────────────────────────────
   164MB 를 올리면 몇 분이 걸린다. 아무 반응이 없으면 사람이 창을 닫는다.
   그래서 진행 칸을 **목록 맨 위**에 띄우고 퍼센트·남은 시간·취소를 낸다.
   fetch 는 올리는 진행률을 주지 않으므로 XHR 을 쓴다. */
let upload = null;             // {xhr, cancelled}

function hsize(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
  if (bytes >= 1024) return Math.round(bytes / 1024) + 'KB';
  return bytes + 'B';
}

function leftLabel(seconds) {
  if (!isFinite(seconds) || seconds <= 0) return '';
  if (seconds < 60) return ' · ' + Math.max(1, Math.round(seconds)) + '초쯤 남음';
  return ' · ' + Math.round(seconds / 60) + '분쯤 남음';
}

function showProgress(name, loaded, total, startedAt) {
  const box = $('dupnow');
  const pct = total ? Math.min(100, Math.round(loaded / total * 100)) : 0;
  const elapsed = (Date.now() - startedAt) / 1000;
  const left = loaded > 0 ? elapsed / loaded * (total - loaded) : Infinity;
  box.innerHTML = `<div class="top">
      <span class="nm">${esc(name)}</span>
      <span class="pc mono">${pct}%</span>
      <button type="button" class="x" id="dupcancel" aria-label="취소">✕</button>
    </div>
    <div class="bar2"><i style="width:${pct}%"></i></div>
    <div class="sub mono">${hsize(loaded)} / ${hsize(total)}${leftLabel(left)}</div>
    <div class="sub">큰 파일은 몇 분 걸립니다. 창을 닫지 마세요.</div>`;
  box.hidden = false;
  $('dupcancel').onclick = () => cancelUpload();
}

function hideProgress() { $('dupnow').hidden = true; $('dupnow').innerHTML = ''; }

function cancelUpload(opts) {
  if (!upload) return;
  upload.cancelled = true;
  try { upload.xhr.abort(); } catch (err) { /* 이미 끝났으면 됐다 */ }
  upload = null;
  hideProgress();
  // 취소는 실패가 아니다. 조용히 접되, 사용자가 누른 것이면 그렇다고 말한다.
  if (!(opts && opts.quiet)) fileWarn('올리기를 취소했습니다. 서버에 남은 것은 없습니다.');
}

function putFile(runId, file) {
  return new Promise(resolve => {
    const form = new FormData();
    form.append('upload', file, file.name);
    const xhr = new XMLHttpRequest();
    const startedAt = Date.now();
    upload = {xhr, cancelled: false};
    showProgress(file.name, 0, file.size, startedAt);

    xhr.upload.onprogress = e => {
      if (!upload || upload.cancelled) return;
      showProgress(file.name, e.loaded, e.total || file.size, startedAt);
    };
    xhr.onload = () => {
      const cancelled = !upload || upload.cancelled;
      upload = null;
      hideProgress();
      if (cancelled) { resolve(null); return; }
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (err) { /* 형식이 아니면 아래에서 말한다 */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        // **413 은 우리 응답이 아니다.** 파일이 서버에 닿기 전에 Cloudflare 가
        // 앞에서 끊은 것이라 `data.detail` 이 없다 — 그대로 두면 몇 분을
        // 기다린 끝에 "올리지 못했습니다." 만 보고 이유를 모른 채 끝난다.
        const limits = (detail && detail.attachment_limits) || {};
        if (xhr.status === 413) {
          // 숫자는 상한에서 끌어온다. 못 받아 왔으면 **숫자 없이 말한다** —
          // 코드에 박아 두면 상한을 바꿨을 때 화면이 조용히 거짓말을 한다.
          const cap = limits.tunnel_max_label;
          fileWarn((cap
            ? `바깥에서는 ${cap} 를 넘는 파일을 올릴 수 없습니다. `
            : '이 파일은 바깥에서 올리기에 너무 큽니다. ')
            + '링크로 붙이시거나, 서버가 있는 곳에서 올려 주세요. '
            + '(내려받기에는 이 제한이 없습니다.)');
          resolve(null);
          return;
        }
        // 거절당했으면 왜인지 말한다 — 용량인지 형식인지 권한인지 디스크인지
        fileWarn(data.detail || '올리지 못했습니다.');
        resolve(null);
        return;
      }
      resolve(data);
    };
    xhr.onerror = () => {
      const cancelled = !upload || upload.cancelled;
      upload = null;
      hideProgress();
      // **조용히 삼키지 않는다.** 현장에서는 콘솔을 아무도 안 본다.
      if (!cancelled) fileWarn('올리는 중에 연결이 끊겼습니다. 다시 시도해 주세요.');
      resolve(null);
    };
    xhr.onabort = () => { hideProgress(); resolve(null); };

    xhr.open('POST', `/board/task/${runId}/files`);
    xhr.send(form);
  });
}

/* **보내기 전에 크기를 본다.**

   서버도 상한을 보지만, 서버는 본문을 읽는 **도중에** 400/507 로 답한다.
   클라이언트가 아직 보내는 중에 답이 오면 XHR 이 `onerror` 로 떨어져서,
   애써 쓴 "파일이 너무 큽니다" 가 화면에 도착하지 못한다 — 사람은 몇 분을
   기다린 끝에 "연결이 끊겼습니다" 만 보고 이유를 모른 채 끝난다.
   상한은 이미 `limits` 로 화면에 와 있으므로 여기서 먼저 거른다.

   돌려주는 것: 'ok' | 'too-big' | 'tunnel' */
function preflight(file) {
  const limits = (detail && detail.attachment_limits) || {};
  if (limits.max_bytes && file.size > limits.max_bytes) {
    fileWarn(`${file.name} 은(는) ${hsize(file.size)} 라 너무 큽니다. `
      + `${limits.max_label} 까지 올릴 수 있습니다. 큰 것은 링크로 붙여 주세요.`);
    return 'too-big';
  }
  if (limits.tunnel_max_bytes && file.size > limits.tunnel_max_bytes) return 'tunnel';
  return 'ok';
}

async function sendFiles(fileList) {
  if (!cur || !fileList || !fileList.length) return;
  fileWarn('');
  for (const file of fileList) {
    const verdict = preflight(file);
    if (verdict === 'too-big') return;              // 이유는 preflight 가 말했다
    if (verdict === 'tunnel') {
      // **막지 않는다.** 집 안 회선에서는 올라간다 — 서버가 있는 곳에서
      // 올리면 되는 것을 못 하게 만들면 안 된다. 대신 미리 말해 준다.
      const limits = detail.attachment_limits || {};
      const go = confirm(
        `${file.name} 은(는) ${hsize(file.size)} 입니다.\n\n`
        + `${limits.tunnel_max_label} 를 넘는 파일은 바깥(인터넷)에서 올릴 때 `
        + '실패합니다. 링크로 붙이시거나, 서버가 있는 곳에서 올려 주세요.\n'
        + '(내려받기에는 이 제한이 없습니다.)\n\n'
        + '그래도 올려 보시겠습니까?');
      if (!go) {
        fileWarn(`${file.name} 을(를) 올리지 않았습니다. `
          + `${limits.tunnel_max_label} 를 넘는 것은 링크로 붙이는 편이 확실합니다.`);
        return;
      }
    }
    const data = await putFile(cur, file);
    if (!data) return;                 // 실패·취소하면 뒤엣것도 올리지 않는다
    applyFiles(data);
  }
}

$('dfiles').addEventListener('click', async e => {
  const open = e.target.closest('[data-fmenu]');
  if (open) {
    const menu = open.nextElementSibling, was = menu.classList.contains('on');
    closeMenus();
    menu.classList.toggle('on', !was);
    return;
  }
  const act = e.target.closest('[data-fact]');
  if (!act) {
    // 줄 자체를 누르면 연다 — 파일은 내려받고 링크는 새 탭에서
    const row = e.target.closest('.fitem');
    if (!row || e.target.closest('.rename')) return;
    const f = (detail.attachments || []).find(x => String(x.id) === String(row.dataset.file));
    if (f) openAttachment(f);
    return;
  }
  const item = act.closest('.fitem');
  const id = item.dataset.file;
  const file = (detail.attachments || []).find(f => String(f.id) === String(id));
  closeMenus();
  if (!file) return;

  if (act.dataset.fact === 'download' || act.dataset.fact === 'open') {
    openAttachment(file);
    return;
  }

  if (act.dataset.fact === 'rename') {
    const mid = item.querySelector('.mid');
    mid.insertAdjacentHTML('beforeend',
      `<span class="rename"><input type="text" value="${esc(file.name)}"
         aria-label="${file.is_link ? '설명' : '새 이름'}">
        <button class="pri" data-frename="${id}">저장</button>
        <button data-fcancel="1">취소</button></span>`);
    const input = mid.querySelector('.rename input');
    input.focus();
    if (file.is_link) input.setSelectionRange(0, input.value.length);
    else input.setSelectionRange(0, input.value.lastIndexOf('.') + 1 || input.value.length);
    return;
  }

  if (act.dataset.fact === 'delete') {
    const what = file.is_link ? '링크' : '파일';
    if (!confirm(`${file.name} ${what}을(를) 지웁니다. 되돌릴 수 없습니다.`)) return;
    const res = await fetch(`/board/task/${cur}/files/${id}/delete`, {method: 'POST'});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { fileWarn(data.detail || '지우지 못했습니다.'); return; }
    applyFiles(data);
  }
});

/* 링크는 우리 서버에 없다 — 새 탭에서 연다. noopener 없이 열면 그 페이지가
   이 창을 건드릴 수 있다. */
function openAttachment(f) {
  if (f.is_link) window.open(f.url, '_blank', 'noopener,noreferrer');
  else location.href = f.url;
}

$('dfiles').addEventListener('click', async e => {
  const cancel = e.target.closest('[data-fcancel]');
  if (cancel) { renderFiles(detail); return; }
  const save = e.target.closest('[data-frename]');
  if (!save) return;
  const id = save.dataset.frename;
  const input = save.closest('.rename').querySelector('input');
  const res = await fetch(`/board/task/${cur}/files/${id}/rename`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: input.value}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { fileWarn(data.detail || '이름을 바꾸지 못했습니다.'); return; }
  applyFiles(data);
});

/* 끌어다 놓는 자리 */
(() => {
  const drop = $('ddrop'), input = $('dfileinput');
  if (!drop || !input) return;
  $('dpick').onclick = () => input.click();
  input.onchange = () => { sendFiles(input.files); input.value = ''; };
  ['dragenter', 'dragover'].forEach(t => drop.addEventListener(t, e => {
    e.preventDefault(); drop.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, e => {
    e.preventDefault(); drop.classList.remove('over');
  }));
  drop.addEventListener('drop', e => { sendFiles(e.dataTransfer.files); });
})();

/* ── 진단 패널 — 패널 이름이 판정 결과다 (CLAUDE.md 4-10) ──────────
   판정은 서버가 계산한다. 화면은 그것을 그대로 보여줄 뿐 다시 판단하지 않는다.
   기한이 지났어도 막는 요인이 없으면 '진행 가능' 이다 — 진행 불가는 남을
   기다리는 상태, 진행 가능인데 안 된 건 우리가 안 한 상태다. */
function renderDiag(d) {
  const dg = $('diag');
  const g = d.diagnosis;
  if (!g) { dg.className = 'diag'; return; }
  dg.className = 'diag g-' + g.tone;
  $('dgTtl').textContent = g.verdict;
  const rows = (g.reasons || []).map(r =>
    `<li><span class="ic">${esc(r.kind)}</span><span>${esc(r.text)}</span></li>`).join('');
  $('dgB').innerHTML =
    `<div class="dg-v ${g.tone}">${esc(g.summary)}</div>` +
    (rows ? `<ul>${rows}</ul>` : '') +
    `<div class="src">보드 전체의 일정 · 상태 · 선후행 관계를 함께 봤습니다.
      상황이 바뀌면 다시 판단합니다.</div>`;
}

// '다시 분석' 과 상태 변경은 같은 일을 한다 — 판정을 다시 받아 온다.
// 두 벌로 두면 한쪽만 고쳐진다.
$('dgR').onclick = () => { if (cur !== null) refreshDiag(cur); };

/* ── 업무 규칙 ── */
function renderRules() {
  const box = $('drules');
  const text = (detail.rules || '').trim();
  box.innerHTML = text
    ? `<div class="ruletext">${esc(text)}</div>`
    : '<div class="empty">아직 적어 둔 규칙이 없습니다.</div>';
  if (detail.can_edit) {
    box.insertAdjacentHTML('beforeend',
      `<button class="ruleedit" id="drulesopen">${text ? '규칙 고치기' : '규칙 적기'}</button>`);
    $('drulesopen').onclick = () => {
      $('drulesbody').value = detail.rules || '';
      $('drulesedit').hidden = false;
      $('drules').hidden = true;
      $('drulesbody').focus();
    };
  }
  $('drulesedit').hidden = true;
  box.hidden = false;
}

$('drulescancel').onclick = () => {
  $('drulesedit').hidden = true;
  $('drules').hidden = false;
};

$('drulessave').onclick = async () => {
  const body = $('drulesbody').value;
  const res = await fetch(`/board/task/${cur}/rules`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({body}),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '저장하지 못했습니다.'); return; }
  detail.rules = (await res.json()).rules;
  renderRules();
};

/* ── 논의 내역 ── */
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
  $('dlog').innerHTML = html;
}

/* 써 놓은 논의를 그 자리에서 고친다. 말을 바꾸는 것(취소선 + 후속 기록)과
   잘못 쓴 것을 바로잡는 것은 다르므로, 이건 오타·오기를 위한 자리다. */
$('dlog').addEventListener('click', async e => {
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
  if (window.ListInput) window.ListInput.attach(box);   // 나중에 그린 칸
  box.style.height = Math.max(56, box.scrollHeight) + 'px';
  box.focus();
  box.setSelectionRange(box.value.length, box.value.length);
}

$('dcancelnew').onclick = () => {
  $('dbody').value = '';
  $('dsuper').checked = false;
};

$('dsave').onclick = async () => {
  const box = $('dbody');
  const body = box.value.trim();
  if (!body || !cur) return;
  const supersede = $('dsuper').checked;
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
  $('dsuper').checked = false;
  renderLog();
};

/* ── 연결된 업무 목록: 열기 / 이동 ── */
function closeMenus() {
  document.querySelectorAll('.menu.on').forEach(m => m.classList.remove('on'));
  $('statmenu').classList.remove('on');
}

$('drel').onclick = e => {
  const act = e.target.closest('[data-act]');
  if (act) {
    const id = act.closest('.relitem').querySelector('.rb').dataset.rel;
    closeMenus();
    if (act.dataset.act === 'open') { openDrawer(id); call('link', id); }
    else call('goTo', id);
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
  const menu = $('statmenu'), r = btn.getBoundingClientRect();
  // 같은 배지를 다시 누르면 상태를 바꾸지 않고 목록만 닫는다
  if (menu.classList.contains('on')) { closeMenus(); return; }
  menu.innerHTML = Object.entries(STATUS).map(([key, v]) =>
    `<button data-s="${esc(key)}"><span class="cv" style="background:${esc(v.color)}"></span>${esc(v.label)}</button>`).join('');
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
  // 자기 화면을 어떻게 고쳐 그릴지는 화면이 안다 — 보드는 바를, 달력은 점을.
  // **다시 불러오지 않는다.** 달력은 보던 달과 칩을 잃으면 안 된다.
  // `view.status` 가 상태를 들고 오므로 따로 넘기지 않는다 — 같은 값이
  // 두 자리에 있으면 어긋났을 때 어느 쪽이 맞는지 알 수 없다.
  call('onStatus', runId, view);
  if (detail) { detail.status = status; renderDrawer(); }
  refreshDiag(runId);
}

/* 상태를 바꾸면 **판정도 바뀐다.** 상태는 판정에 들어가는 값이므로
   (CLAUDE.md 4-10 의 1번: `status == '완료'` 면 맨 위에서 끊는다),
   손대지 않은 옛 판정을 그대로 다시 그리면 완료로 바꿔도 위쪽에
   '진행 불가' 가 남는다. **패널 이름이 판정 결과인 화면**이라 더 그렇다.

   받아 오는 동안에는 판정이 옛것임이 보이게 흐려 둔다. 그리고
   **실패해도 패널은 살아 있어야 한다** (4-10 조건 8) — 판정 한 자리가
   비는 것으로 끝나야지, 나머지 근거까지 사라지면 안 된다. */
async function refreshDiag(runId) {
  const dg = $('diag');
  dg.classList.add('busy');
  try {
    const res = await fetch(`/board/task/${runId}`, {headers: {'Accept': 'application/json'}});
    if (!res.ok) return;
    const fresh = await res.json();
    // 그 사이에 다른 업무를 열었으면 남의 판정을 덮어쓰지 않는다
    if (!detail || String(cur) !== String(fresh.run_id)) return;
    detail.diagnosis = fresh.diagnosis;
    renderDiag(detail);
  } catch (err) {
    // 못 받아 왔으면 옛 판정을 그대로 둔다. 지우면 근거까지 사라진다.
  } finally {
    dg.classList.remove('busy');
  }
}

/* ── 노션처럼 쓰는 입력칸 ──────────────────────────────────────────
   **코드는 `static/js/listinput.js` 한 벌이다.** 회의록 화면(2단계)이 같은
   입력을 쓰게 되면서 밖으로 뺐다 — 베껴 두면 한쪽만 고쳐지고, 그 갈림을
   아무도 눈치채지 못한다. 여기서는 붙이기만 한다. */
if (window.ListInput) window.ListInput.attachAll();

/* ── 달력 탭 — 업무 하나의 기간을 본다 (사이드바의 달력 화면과 다르다) ── */
function calendar(d) {
  const el = $('dcal');
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
      const dots = (marks[iso] || []).slice(0, 4).map(c => `<i style="background:${esc(c)}"></i>`).join('');
      out += `<div class="${cls}">${day}<span class="dots">${dots}</span></div>`;
    }
    cursor.setMonth(cursor.getMonth() + 1);
  }
  el.innerHTML = out;
}

/* ── 폭 조절 ── */
const grip = $('grip');
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
    call('afterLayout');
    removeEventListener('mousemove', move);
    removeEventListener('mouseup', up);
  };
  addEventListener('mousemove', move);
  addEventListener('mouseup', up);
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
    relitem: at('.relitem') || at('.fitem'),
    // 무엇이 '업무를 여는 것' 인지는 화면마다 다르다 — 보드는 바와 업무명,
    // 달력은 점이다. 그래서 host 가 판단한다.
    task: !!(e.target instanceof Element) && !!call('isTaskClick', e.target),
    chrome: at('header') || at('.toolbar') || at('.calbar') || at('.sidenav'),
  };
}, true);

addEventListener('click', () => {
  const from = clickOrigin || {};
  clickOrigin = null;
  if (Date.now() - dragEnd < 400) return;
  if (!from.relitem && !from.statmenu && !from.statchip) closeMenus();
  if (!dw.classList.contains('open')) return;
  if (from.drawer || from.statmenu) return;
  if (from.task) return;                  // 다른 업무를 여는 동작이다
  if (from.chrome) return;                // 소속 선택·필터를 만질 때 닫히면 불편하다
  closeDrawer();
});

/* ── 바깥에서 쓰는 것 ── */
window.Drawer = {
  init(options) {
    host = options || {};
    // 알림을 누르고 들어오면 그 업무의 상세 패널을 열어 준다 (?task=123).
    // 달력에서도 같은 길이다 — `/calendar?task=123` 으로 열린 채 시작한다.
    const wanted = new URLSearchParams(location.search).get('task');
    if (!wanted) return;
    const run = Number(wanted);
    if (call('meta', run) === null) return;      // 이 화면에 없는 업무면 그만둔다
    if (typeof host.openFromUrl === 'function') host.openFromUrl(run);
    else openDrawer(run);
  },
  open: openDrawer,
  close: closeDrawer,
  isOpen: () => dw.classList.contains('open'),
  current: () => cur,
  /* 드래그 직후인가. 보드가 바를 끌 때도 같은 값을 쓴다 —
     두 벌로 두면 한쪽만 초기화돼 클릭이 새어 나간다. */
  recentDrag: () => Date.now() - dragEnd < 400,
  noteDrag: () => { dragEnd = Date.now(); },
  /* 보드가 바를 끌어 날짜를 옮긴 뒤, 열려 있는 패널도 맞춘다 */
  applyDates(runId, saved) {
    if (!detail || String(detail.run_id) !== String(runId)) return;
    detail.start = saved.start;
    detail.end = saved.end;
    renderDrawer();
  },
};
})();
