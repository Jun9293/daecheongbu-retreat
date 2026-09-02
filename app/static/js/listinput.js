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

function attachAll(root) {
  (root || document).querySelectorAll('textarea[data-listedit]').forEach(attach);
}

window.ListInput = {attach, attachAll, BULLETS, LIST_RE};
attachAll();
})();
