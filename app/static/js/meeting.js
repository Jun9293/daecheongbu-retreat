/* 회의록 제안 — 고른 것만 반영한다 (CLAUDE.md 회의록 4단계).
 *
 * **아무것도 자동으로 반영되지 않는다.** 사람이 하나씩 누른다.
 *
 * **실패해도 화면은 살아 있어야 한다** (4-10 조건 8). 제안을 못 받아 오면
 * 그 자리에 한 줄이 뜨는 것으로 끝나고, 회의록 본문은 그대로 읽힌다 —
 * 여기서 터져서 회의록을 못 보게 되면 안 된다.
 */
(function () {
'use strict';

const box = document.querySelector('.mt-sug');
if (!box) return;
const list = box.querySelector('.mt-sug-list');
const meetingId = box.dataset.meeting;
const canEdit = box.dataset.canEdit === '1';

const esc = s => String(s == null ? '' : s)
  .replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

function 그린다(items) {
  if (!items.length) {
    // **할 말이 없으면 빈 목록** (조건 4). 억지로 만들면 근거 없는 제안이 된다
    list.innerHTML = '<p class="mt-sug-none">붙일 만한 업무를 찾지 못했습니다.</p>';
    return;
  }
  // **두 가지는 다르게 그린다.**
  //   논의 — 붙일 업무가 있다. 눌러서 그 업무의 논의로 남긴다
  //   새 업무 — 붙일 곳이 없다. **단추를 두지 않는다** — 누를 곳이 없는
  //            단추를 보여 주느니 어디서 만드는지를 말한다 (보드의 `+ 업무 추가`).
  //            없는 기능을 있는 것처럼 보이게 하지 않는다
  list.innerHTML = items.map(x => x.kind === 'new' ? `
    <div class="mt-sug-row is-new">
      <div class="mt-sug-main">
        <b>${esc(x.text)}</b>
        <span class="mt-sug-why">${esc(x.why)}</span>
      </div>
      <span class="mt-sug-where">보드의 <b>+ 업무 추가</b> 에서</span>
    </div>` : `
    <div class="mt-sug-row" data-run="${x.run_id}">
      <div class="mt-sug-main">
        <b>${esc(x.run_title)}</b>
        <span class="mt-sug-why">${esc(x.why)}</span>
      </div>
      ${canEdit ? `<button type="button" data-apply="${x.run_id}">이 업무에 남기기</button>` : ''}
    </div>`).join('');
}

async function 불러온다() {
  try {
    const res = await fetch(`/meetings/${meetingId}/suggestions`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    if (data.failed) {
      list.innerHTML = '<p class="mt-sug-none">제안을 만들지 못했습니다 —'
        + ' 회의록은 그대로 보실 수 있습니다.</p>';
      return;
    }
    그린다(data.items || []);
  } catch (e) {
    // 조건 8 — 여기서 죽어도 회의록 본문은 살아 있다
    list.innerHTML = '<p class="mt-sug-none">제안을 불러오지 못했습니다 —'
      + ' 회의록은 그대로 보실 수 있습니다.</p>';
  }
}

list.addEventListener('click', async e => {
  const btn = e.target.closest('[data-apply]');
  if (!btn) return;
  const row = btn.closest('.mt-sug-row');
  btn.disabled = true;
  btn.textContent = '남기는 중…';
  try {
    const res = await fetch(`/meetings/${meetingId}/suggestions/apply`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({run_id: Number(btn.dataset.apply)}),
    });
    if (!res.ok) throw new Error(res.status);
    const saved = await res.json();
    row.classList.add('done');
    // **되돌리는 길을 말해 준다** — 남긴 것을 지우려면 그 업무의 논의에서 한다
    row.querySelector('.mt-sug-why').textContent =
      `남겼습니다 — 「${saved.run_title}」 의 논의. 지우려면 그 업무의 논의 탭에서.`;
    btn.remove();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = '이 업무에 남기기';
    // 조용히 삼키지 않는다 — 눌렀다고 믿은 채로 넘어가면 안 된다 (5-0)
    row.querySelector('.mt-sug-why').textContent = '남기지 못했습니다. 다시 눌러 주세요.';
  }
});

불러온다();
})();
