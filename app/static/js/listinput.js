/* 노션처럼 쓰는 입력칸 — **한 벌** (CLAUDE.md 4-9 · 회의록 2단계).
 *
 * 번호를 매기고 엔터를 치면 다음 번호가 자동으로 붙고, 하이픈에 스페이스를
 * 치면 글머리표가 된다. 탭으로 한 단계 들어가고 시프트+탭으로 나온다.
 * 빈 항목에서 엔터를 치면 목록을 빠져나온다.
 *
 * **원래 `drawer.js` 안에 있었다.** 회의록 화면이 같은 입력을 쓰게 되면서
 * 밖으로 뺐다 — 베껴 두면 한쪽만 고쳐지고, 그 갈림을 아무도 눈치채지 못한다.
 * 이 프로젝트에서 가장 자주 고쳐 온 문제라 처음부터 한 벌로 둔다.
 *
 * 쓰는 법 — `<textarea data-listedit>` 를 두면 알아서 붙는다.
 * 나중에 그린 칸에는 `ListInput.attach(box)`.
 */
(function () {
'use strict';

const BULLETS = ['•', '◦', '▪'];
const LIST_RE = /^(\s*)(?:([•◦▪-])|(\d+)\.)\s(.*)$/;

function lineAt(box) {
  const value = box.value, pos = box.selectionStart;
  const from = value.lastIndexOf('\n', pos - 1) + 1;
  let to = value.indexOf('\n', pos);
  if (to < 0) to = value.length;
  return {from, to, text: value.slice(from, to)};
}

function replaceLine(box, line, text, caret) {
  const value = box.value;
  box.value = value.slice(0, line.from) + text + value.slice(line.to);
  const at = line.from + (caret === undefined ? text.length : caret);
  box.setSelectionRange(at, at);
}

function attach(box) {
  if (!box || box.dataset.listOn) return;
  box.dataset.listOn = '1';                 // 두 번 붙으면 엔터가 두 줄 들어간다
  box.addEventListener('keydown', e => {
    const line = lineAt(box);
    const m = line.text.match(LIST_RE);

    if (e.key === 'Enter' && !e.shiftKey && m) {
      const [, indent, bullet, num, body] = m;
      e.preventDefault();
      if (!body.trim()) {                     // 빈 항목 → 목록에서 빠져나온다
        replaceLine(box, line, indent.slice(0, -2));
        return;
      }
      const next = num ? `${indent}${Number(num) + 1}. ` : `${indent}${bullet} `;
      const at = box.selectionStart;
      box.value = box.value.slice(0, at) + '\n' + next + box.value.slice(at);
      const caret = at + 1 + next.length;
      box.setSelectionRange(caret, caret);
      return;
    }

    if (e.key === 'Tab') {
      e.preventDefault();
      if (!m) {                                // 목록이 아니면 두 칸 들여쓰기
        const at = box.selectionStart;
        if (e.shiftKey) return;
        box.value = box.value.slice(0, at) + '  ' + box.value.slice(at);
        box.setSelectionRange(at + 2, at + 2);
        return;
      }
      const [, indent, bullet, num, body] = m;
      const depth = Math.floor(indent.length / 2);
      const next = e.shiftKey ? Math.max(0, depth - 1) : depth + 1;
      const pad = '  '.repeat(next);
      const marker = num ? '1.' : BULLETS[Math.min(next, BULLETS.length - 1)];
      replaceLine(box, line, `${pad}${marker} ${body}`);
      return;
    }

    if (e.key === ' ') {                       // "- " 나 "* " 를 글머리표로
      const plain = line.text.match(/^(\s*)([-*])$/);
      if (plain && box.selectionStart === line.to) {
        e.preventDefault();
        const depth = Math.floor(plain[1].length / 2);
        replaceLine(box, line, `${plain[1]}${BULLETS[Math.min(depth, BULLETS.length - 1)]} `);
      }
    }
  });
}

/* ── 내용만큼 길어지는 칸 ────────────────────────────────────────────
   회의록 본문처럼 **길게 적는 칸**은 손잡이로 늘리게 두지 않는다 — 칸
   안에 스크롤이 생기면 위에 적은 것을 보려고 두 번 스크롤하게 되고,
   손잡이는 매번 사람이 끌어야 한다. 내용이 늘면 칸이 따라 늘어난다.

   **켜는 곳에만 붙는다**(`data-autogrow`). 논의 입력칸(4-9)은 드로어
   안이라 패널이 통째로 길어지면 안 되므로 켜지 않는다 — 같은 코드를
   두 벌로 만들지 않되, 어디에 쓸지는 그 자리가 정한다.

   높이는 `scrollHeight` + 테두리다. `box-sizing:border-box` 라
   테두리를 안 더하면 그만큼 모자라 **1px 스크롤이 남는다.** */
function grow(box) {
  if (!box) return;
  const 테두리 = box.offsetHeight - box.clientHeight;   // 위아래 테두리
  box.style.height = 'auto';        // 줄어드는 쪽도 재려면 먼저 풀어야 한다
  box.style.height = (box.scrollHeight + 테두리) + 'px';
}

function autogrow(box) {
  if (!box || box.dataset.growOn) return;
  box.dataset.growOn = '1';
  // JS 가 죽으면 CSS 의 스크롤로 물러선다 — 그때 감춰 두면 글이 잘린다
  box.style.overflowY = 'hidden';
  // 붙여넣기·지우기·자동 채움까지 한 이벤트로 (input) — 처음 그릴 때도 한 번
  box.addEventListener('input', () => grow(box));
  grow(box);
}

function attachAll(root) {
  const 안 = root || document;
  안.querySelectorAll('textarea[data-listedit]').forEach(attach);
  안.querySelectorAll('textarea[data-autogrow]').forEach(autogrow);
}

window.ListInput = {attach, attachAll, autogrow, grow, BULLETS, LIST_RE};
attachAll();
// 글꼴이 늦게 오면 줄 수가 달라진다 — 준비된 뒤 한 번 더 잰다
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => {
    document.querySelectorAll('textarea[data-autogrow]').forEach(grow);
  });
}
})();
