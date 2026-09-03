/* 회의록 제안 — 고른 것만 반영한다 (CLAUDE.md 회의록 4·5단계).
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
 * ## 비어 있는 것이 세 가지 뜻을 갖지 않게 한다
 *
 * `state` 가 셋을 가른다 — **도는중** · **됨** · **실패**. 사람이 할 일이
 * 전부 다르다: 기다린다 / 읽는다 / 다시 누른다. 하나로 뭉치면 기다려야 할
 * 때 포기하고, 다시 눌러야 할 때 기다린다.
 *
 * ## 무엇으로 골랐는지 화면이 말한다
 *
 * 문장으로 읽었는지 낱말이 겹치는 정도로 골랐는지를 위에 적는다 (6-3).
 * **물러선 것을 감추면 실제로 어떤지 영영 모른다.**
 *
 * **실패해도 화면은 살아 있어야 한다** (4-10 조건 8). 제안을 못 받아 오면
 * 그 자리에 한 줄이 뜨는 것으로 끝나고, 회의록 본문은 그대로 읽힌다.
 */
(function () {
'use strict';

const box = document.querySelector('.mt-sug');
if (!box) return;
const list = box.querySelector('.mt-sug-list');
const how = box.querySelector('.mt-sug-how');
const meetingId = box.dataset.meeting;
let canEdit = box.dataset.canEdit === '1';

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
  if (x.kind === 'decision') {
    // **회의록의 줄을 그대로 보여준다.** 사람이 인용을 보면 3초 만에
    // 맞는지 안다 — 요약만 있으면 원문으로 돌아가 확인해야 한다 (6-3)
    return `<div class="mt-sug-row is-decision"><div class="mt-sug-main">
      <p class="mt-do"><i class="mt-kind">결정사항</i>${esc(x.action)}</p>
      <blockquote class="mt-quote">${esc(x.quote)}</blockquote>
      ${출처}</div></div>`;
  }
  if (x.kind === 'new') {
    // 붙일 곳이 없다 — 단추 대신 어디서 만드는지를 말한다
    const 곁 = [x.parent_title ? `「${x.parent_title}」 의 하위` : '',
                x.department || ''].filter(Boolean).join(' · ');
    return `<div class="mt-sug-row is-new"><div class="mt-sug-main">
      <p class="mt-do"><i class="mt-kind">새 업무로 만들기</i>${esc(x.action)}</p>
      ${곁 ? `<p class="mt-where-to">${esc(곁)}</p>` : ''}
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

function 그린다(data) {
  const items = data.items || [];
  if (data.state === '도는중') {
    list.innerHTML = '<p class="mt-sug-none">회의 내용을 읽는 중입니다…</p>';
    return;
  }
  if (data.state === '실패') {
    list.innerHTML = '<p class="mt-sug-none">'
      + esc(data.note || '분석하지 못했습니다.')
      + ' 회의록은 그대로 보실 수 있습니다.' + 다시단추() + '</p>';
    return;
  }
  if (!items.length) {
    // **할 말이 없으면 빈 목록** (조건 4). 억지로 만들면 근거 없는 제안이 된다
    list.innerHTML = '<p class="mt-sug-none">이 회의록에서 낼 것을 찾지 못했습니다.'
      + 다시단추() + '</p>';
    return;
  }
  list.innerHTML = items.map(줄).join('');
}

/* 무엇으로 골랐는가 + 사람 평가 표시. **둘 다 감추지 않는다.** */
function 머리말(data) {
  if (!how) return;
  const 조각 = [];
  // **끝난 것만 "골랐습니다" 라고 말한다.** 실패했는데 지난번 방식이 남아
  // 있다고 "읽고 골랐습니다" 를 띄우면, 화면이 위아래에서 서로를 부정한다
  // (아래 목록에는 401 이 떠 있다)
  if (data.state === '됨' && data.how === '문장') {
    조각.push('<b>회의 내용을 읽고 골랐습니다.</b>');
  } else if (data.state === '됨' && data.how === '낱말') {
    조각.push('<b>회의록과 이름이 겹치는 업무입니다. 내용을 읽지는 않았습니다.</b>');
  } else if (data.state === '도는중') {
    조각.push('<b>회의 내용을 읽고 있습니다.</b>');
  } else if (data.state === '실패') {
    조각.push('<b>이번에는 읽지 못했습니다.</b>');
  }
  if (data.note && data.state !== '실패') 조각.push(esc(data.note));
  how.innerHTML = 조각.join(' ');
  // 사람 평가 (6단계) — **보내는 것과 남기는 것은 다르다.** 이 회의록에
  // 그런 대목이 있다는 것만 말하고, 제안에는 인용되지 않는다
  let 알림 = box.querySelector('.mt-people');
  if (data.people_notes && data.people_notes.length) {
    if (!알림) {
      알림 = document.createElement('p');
      알림.className = 'mt-people';
      how.after(알림);
    }
    알림.innerHTML = '이 회의록에는 <b>사람에 대한 평가로 보이는 대목</b>이'
      + ` ${data.people_notes.length}줄 있습니다 (9장).`
      + ' 제안에는 그 대목을 담지 않습니다.';
  } else if (알림) {
    알림.remove();
  }
}

function 다시단추() {
  return canEdit
    ? ' <button type="button" class="mt-retry">다시 시도</button>'
    : '';
}

let 기다림 = null;

async function 불러온다() {
  try {
    const res = await fetch(`/meetings/${meetingId}/suggestions`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    if (typeof data.can_edit === 'boolean') canEdit = data.can_edit;
    머리말(data);
    그린다(data);
    // 도는 중이면 다시 물어본다. **끝나면 저절로 나타나야 한다** —
    // 사람이 새로고침해야 보이면 아무도 안 기다린다
    if (data.state === '도는중') {
      clearTimeout(기다림);
      기다림 = setTimeout(불러온다, 3000);
    }
  } catch (e) {
    // 조건 8 — 여기서 죽어도 회의록 본문은 살아 있다
    list.innerHTML = '<p class="mt-sug-none">제안을 불러오지 못했습니다 —'
      + ' 회의록은 그대로 보실 수 있습니다.' + 다시단추() + '</p>';
  }
}

list.addEventListener('click', async e => {
  const 다시 = e.target.closest('.mt-retry');
  if (다시) {
    다시.disabled = true;
    try {
      await fetch(`/meetings/${meetingId}/suggestions/rerun`, {method: 'POST'});
    } catch (err) { /* 아래에서 다시 물어본다 */ }
    불러온다();
    return;
  }
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
