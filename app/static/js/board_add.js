/* 회차를 연 뒤 업무를 더 넣는 화면 */
(function () {
'use strict';
const $ = id => document.getElementById(id);
const sel = new Set();
const lib = $('addLib');

if (lib) {
  lib.querySelectorAll('.trow[data-i]').forEach(row => row.onclick = () => {
    const id = row.dataset.i;
    sel.has(id) ? sel.delete(id) : sel.add(id);
    row.classList.toggle('on', sel.has(id));
    row.classList.toggle('off', !sel.has(id));
    $('pickCount').textContent = sel.size;
    $('addExisting').disabled = sel.size === 0;
  });

  $('addExisting').onclick = async () => {
    const res = await fetch('/board/add/existing', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({library_ids: [...sel].map(Number)}),
    });
    if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '추가하지 못했습니다.'); return; }
    location.href = (await res.json()).redirect;
  };
}

/* 하위를 고르면 상위 업무를 함께 정해야 한다 */
$('nkind').onchange = () => {
  $('parentField').hidden = $('nkind').value !== 'sub';
};

/* 마감이 시작보다 앞서지 않게 서로 끌어준다 */
const start = $('nstart'), end = $('nend');
start.onchange = () => { if (end.value < start.value) end.selectedIndex = start.selectedIndex; };
end.onchange = () => { if (end.value < start.value) start.selectedIndex = end.selectedIndex; };

$('addNew').onclick = async () => {
  const title = $('ntitle').value.trim();
  if (!title) { $('ntitle').focus(); return; }
  const kind = $('nkind').value;
  if (kind === 'sub' && !$('nparent').value) { alert('상위 업무를 골라주세요.'); return; }
  const res = await fetch('/board/add/new', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      title,
      department_key: $('ndept').value,
      kind,
      start: start.value,
      end: end.value,
      parent_library_id: kind === 'sub' ? Number($('nparent').value) : null,
    }),
  });
  if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '만들지 못했습니다.'); return; }
  location.href = (await res.json()).redirect;
};
})();
