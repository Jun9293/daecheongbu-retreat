/* 업무 라이브러리 — 선후행 지정 (CLAUDE.md 2장 · 6-3).
 *
 * 선행은 방향이 있고 기다리는 쪽에만 적는다. 여기서 A 에 B 를 넣어도 B 에는
 * 아무것도 쓰지 않는다 — 후속은 서버가 역방향으로 계산해 보여준다.
 * 제안은 제안일 뿐이라 누르기 전에는 저장하지 않는다.
 */
const FLAT = window.__FLAT || [];
const byId = new Map(FLAT.map(r => [r.library_id, r]));
const $ = id => document.getElementById(id);

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
}

/* ── 목록 좁혀 찾기 — 102건을 눈으로 훑을 수는 없다 ── */
$('pfind').addEventListener('input', e => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('#prelist .prow').forEach(row => {
    row.hidden = q ? !row.dataset.name.toLowerCase().includes(q) : false;
  });
});

/* ── 선행 고르기 ── */
let editing = null;

function openPicker(libraryId, preselect) {
  const row = byId.get(libraryId);
  if (!row) return;
  editing = libraryId;
  const chosen = new Set(preselect || row.prerequisites || []);
  $('pretitle').textContent = `${row.title} 이(가) 기다릴 업무`;
  $('prewarn').hidden = true;
  $('pmfind').value = '';
  $('pmlist').innerHTML = FLAT
    .filter(r => r.library_id !== libraryId)
    .map(r => `<label data-name="${esc(r.title)}${r.parent_title ? ' ' + esc(r.parent_title) : ''}">
        <input type="checkbox" value="${r.library_id}" ${chosen.has(r.library_id) ? 'checked' : ''}>
        <span>${r.depth ? '<span class="sub">↳ </span>' : ''}${esc(r.title)}
          ${r.parent_title ? `<span class="sub">· ${esc(r.parent_title)}</span>` : ''}</span>
        <span class="dw">D-${r.d_week}주</span>
      </label>`).join('');
  $('premodal').hidden = false;
  $('pmfind').focus();
}

function closePicker() {
  $('premodal').hidden = true;
  editing = null;
}

$('pmfind').addEventListener('input', e => {
  const q = e.target.value.trim().toLowerCase();
  $('pmlist').querySelectorAll('label').forEach(el => {
    el.hidden = q ? !el.dataset.name.toLowerCase().includes(q) : false;
  });
});

$('preclose').onclick = closePicker;
$('precancel').onclick = closePicker;
$('premodal').addEventListener('click', e => {
  if (e.target === $('premodal')) closePicker();
});

document.getElementById('prelist').addEventListener('click', e => {
  const btn = e.target.closest('[data-edit]');
  if (btn) openPicker(Number(btn.dataset.edit));
});

async function save(libraryId, ids) {
  const res = await fetch('/library/prerequisites', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({library_id: libraryId, prerequisite_ids: ids}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return {ok: false, detail: data.detail || '저장하지 못했습니다.'};
  return {ok: true, data};
}

$('presave').onclick = async () => {
  if (editing === null) return;
  const ids = [...$('pmlist').querySelectorAll('input:checked')].map(i => Number(i.value));
  const out = await save(editing, ids);
  if (!out.ok) {                       // 위반은 사유를 화면에 그대로 보여준다
    const warn = $('prewarn');
    warn.textContent = out.detail;
    warn.hidden = false;
    warn.style.color = 'var(--now-ink, #8E2A19)';
    return;
  }
  closePicker();
  location.reload();                   // 후속 표시가 다른 줄에도 걸리므로 다시 그린다
};

/* ── 제안 — 누르기 전에는 저장하지 않는다 ── */
document.querySelectorAll('.prop').forEach(btn => {
  btn.onclick = async () => {
    const libraryId = Number(btn.dataset.lib);
    const row = byId.get(libraryId);
    const ids = [...(row ? row.prerequisites : []), Number(btn.dataset.pre)];
    btn.disabled = true;
    const out = await save(libraryId, ids);
    if (!out.ok) { alert(out.detail); btn.disabled = false; return; }
    location.reload();
  };
});
