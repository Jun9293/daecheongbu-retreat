/* 각 팀의 업무 선택 — 임시저장과 제출 (CLAUDE.md 6-6) */
(function () {
'use strict';

const META = JSON.parse(document.getElementById('draft-meta').textContent);
const $ = id => document.getElementById(id);
const lib = $('draftLib');
const sel = new Set();

/* 서버가 그려 준 초기 선택을 그대로 읽어 온다 */
lib.querySelectorAll('.trow[data-i]').forEach(row => {
  if (row.classList.contains('on')) sel.add(row.dataset.i);
});

function paint() {
  lib.querySelectorAll('.tgroup').forEach(group => {
    const row = group.querySelector('.trow[data-i]');
    const on = sel.has(row.dataset.i);
    row.classList.toggle('on', on);
    row.classList.toggle('off', !on);
    group.querySelectorAll('.subrow').forEach(s => s.classList.toggle('off', !on));
  });
  $('pickCount').querySelector('b').textContent = sel.size;
}

if (META.canEdit) {
  lib.querySelectorAll('.trow[data-i]').forEach(row => row.onclick = () => {
    const id = row.dataset.i;
    sel.has(id) ? sel.delete(id) : sel.add(id);
    paint();
  });
}
paint();

async function send(submit) {
  const ids = [...sel];
  const res = await fetch(`/draft/${META.department}/save`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      library_ids: ids.filter(i => !i.startsWith('new:')).map(Number),
      adopted: ids.filter(i => i.startsWith('new:')).map(i => i.slice(4)),
      note: $('note').value,
      submit,
    }),
  });
  if (!res.ok) {
    alert((await res.json().catch(() => ({}))).detail || '저장하지 못했습니다.');
    return;
  }
  const out = await res.json();
  $('hint').textContent = submit
    ? `제출 완료 — ${out.progress.submitted}/${out.progress.total}개 부서`
    : '임시저장됨. 아직 제출하지 않았습니다.';
  if (submit && out.progress.all_in) {
    $('hint').textContent += ' · 모든 팀이 제출했습니다';
  }
}

if (META.canEdit) {
  $('saveDraft').onclick = () => send(false);
  $('submitDraft').onclick = () => send(true);
}
})();
