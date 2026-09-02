/* 회의록 제안 — 고른 것만 반영한다 (CLAUDE.md 회의록 4단계).
 *
 * **아무것도 자동으로 반영되지 않는다.** 사람이 하나씩 누른다.
 *
 * ## 무엇을 하자는 것인지가 먼저다
 *
 * 처음에는 업무 이름과 "왜 골랐는지" 만 있었다 —
 *
 *     PPT 템플릿 제작
 *     회의록과 업무 이름에 '템플릿, PPT, 제작' 이(가) 함께 나옵니다
 *
 * **왜 골랐는지만 있고 무엇을 하자는 것인지가 없었다.** 성적표를 채우려던
 * 사람이 "이 내용 자체가 무슨 말인지 모르겠다" 고 멈췄다. 순서가 뒤집혀
 * 있었다 — 하려는 일이 먼저, 근거는 그 아래 작게 (4-0 — 조용하게).
 *
 * ## 누르기 전에 무엇이 적히는지 보인다
 *
 * 남을 문장을 접어 두었다가 펼쳐 본다 (4-10 이 "무엇을 보고 그렇게 말하는지
 * 함께 보인다" 고 한 자리와 같다). 같은 회의록에서 온 논의가 그 업무에 이미
 * 있으면 **그렇다고 말한다** — 두 번 남으면 어느 것이 맞는지 알 수 없고,
 * 지우는 길은 그 업무의 논의 탭뿐이라 되돌리는 값이 비싸다.
 *
 * **실패해도 화면은 살아 있어야 한다** (4-10 조건 8). 제안을 못 받아 오면
 * 그 자리에 한 줄이 뜨는 것으로 끝나고, 회의록 본문은 그대로 읽힌다.
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

/* 남을 문장 미리보기. **접어 둔다** — 회의록 본문 전체라 길다. */
function 미리보기(x) {
  if (!x.preview) return '';
  return `<details class="mt-peek">
    <summary>남을 내용 보기</summary>
    <pre>${esc(x.preview)}</pre>
  </details>`;
}

function 줄(x) {
  const 머리 = `<p class="mt-do">${esc(x.action)}</p>`;
  const 근거 = `<p class="mt-sug-why">${esc(x.why)}</p>`;
  const 출처 = `<span class="mt-sug-from">${esc(x.from)}</span>`;

  if (x.kind === '더있음') {
    return `<div class="mt-sug-row is-more"><div class="mt-sug-main">
      ${머리}${근거}</div></div>`;
  }
  if (x.kind === 'new') {
    // 붙일 곳이 없다 — 단추 대신 어디서 만드는지를 말한다
    return `<div class="mt-sug-row is-new"><div class="mt-sug-main">
      <p class="mt-do"><i class="mt-kind">새 업무로 만들기</i>${esc(x.action)}</p>
      ${근거}${출처}</div>
      <span class="mt-sug-where">보드의 <b>+ 업무 추가</b> 에서</span></div>`;
  }
  const 이미 = x.already
    ? `<p class="mt-dup">이 회의록에서 온 논의가 <b>이미 있습니다.</b>` +
      ` 다시 누르면 같은 내용이 두 번 남습니다.</p>`
    : '';
  const 단추 = canEdit
    ? `<button type="button" data-apply="${x.run_id}">${
        x.already ? '그래도 남기기' : '남기기'}</button>`
    : '';
  return `<div class="mt-sug-row" data-run="${x.run_id}"><div class="mt-sug-main">
    ${머리}${이미}${근거}${출처}${미리보기(x)}</div>${단추}</div>`;
}

function 그린다(items) {
  if (!items.length) {
    // **할 말이 없으면 빈 목록** (조건 4). 억지로 만들면 근거 없는 제안이 된다
    list.innerHTML = '<p class="mt-sug-none">붙일 만한 업무를 찾지 못했습니다.</p>';
    return;
  }
  list.innerHTML = items.map(줄).join('');
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
    row.querySelector('.mt-do').textContent =
      `남겼습니다 — 「${saved.run_title}」 의 논의. 지우려면 그 업무의 논의 탭에서.`;
    btn.remove();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = '남기기';
    // 조용히 삼키지 않는다 — 눌렀다고 믿은 채로 넘어가면 안 된다 (5-0)
    row.querySelector('.mt-sug-why').textContent = '남기지 못했습니다. 다시 눌러 주세요.';
  }
});

불러온다();
})();
