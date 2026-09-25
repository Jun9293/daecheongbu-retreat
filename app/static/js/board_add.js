/* 업무 추가 — **팝업과 옛 화면(`/board/add`)이 같은 이 파일을 쓴다** (CLAUDE.md 6-7 · 목업 C).

   폼을 살리는 곳은 `살린다()` 하나다. 두 벌이면 한쪽에서만 고쳐지고 갈린 쪽을
   아무도 눈치채지 못한다 — 드로어를 보드·달력·목록이 한 벌로 쓰는 것과 같은 자리(4-13).

   날짜는 **드로어의 기간 줄과 같은 부품**(`DatePick`)이다. 여기서 새로 만들지 않는다.
   고른 것은 화면에만 담아 두고, 서버로는 「새 업무 만들기」 를 누를 때 한 번 간다. */
(function () {
'use strict';
const esc = t => String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

/* 목업 C — 처음 위치는 가로 가운데 · 위 70px (폭 640 은 CSS 가 정한다) */
const 첫위 = 70;
/* 끌기 범위: 가로는 「80px 만 남을 때까지」, 세로는 윗줄 높이(44)만 남을 때까지.
   목업이 적은 −560 은 폭 640 일 때의 그 값이다 — 좁은 화면에서 폭이 줄면
   숫자를 박아 둔 쪽이 틀리므로 폭에서 센다. */
const 남길가로 = 80, 윗줄 = 44;

let 팝업 = null, 되돌릴초점 = null;

const 날짜글 = (s, e) =>
  !s ? '날짜 없음 — 달력 버튼으로 고르기'
  : (s === e || !e) ? s.replace(/-/g, '.')
  : `${s.replace(/-/g, '.')} – ${e.slice(5).replace('-', '.')}`;

function 살린다(root, onSaved) {
  const $ = id => root.querySelector('#' + id);
  const 간다 = onSaved || (() => { location.href = '/board'; });
  /* 까닭 줄 — **참/거짓이면 켜고 끄기만** 한다. 템플릿이 들고 있는 글을 그대로 쓰려고
     그렇다: 끌 때 글자까지 지우면 **다시 켰을 때 빈 줄이 뜬다**(처음에 그랬다).
     글자를 주는 것은 서버가 말한 까닭뿐이다 — 같은 말을 JS 에 또 적지 않는다. */
  const 켠다 = (el, 글) => {
    if (!el) return;
    if (typeof 글 === 'string') el.textContent = 글;
    el.hidden = !글;
  };

  /* ── 라이브러리에서 넣기 ── */
  const lib = $('addLib');
  if (lib) {
    const 고른것 = new Set();
    lib.querySelectorAll('.trow[data-i]').forEach(row => row.onclick = () => {
      const id = row.dataset.i;
      고른것.has(id) ? 고른것.delete(id) : 고른것.add(id);
      row.classList.toggle('on', 고른것.has(id));
      row.classList.toggle('off', !고른것.has(id));
      $('pickCount').textContent = 고른것.size;
      $('addExisting').disabled = 고른것.size === 0;
    });
    $('addExisting').onclick = async () => {
      const res = await fetch('/board/add/existing', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({library_ids: [...고른것].map(Number)}),
      });
      if (!res.ok) { alert((await res.json().catch(() => ({}))).detail || '추가하지 못했습니다.'); return; }
      await res.json();
      간다();
    };
  }

  /* ── 분류 세 칸 — 하위를 고르면 상위 업무 칸이 뜬다 ── */
  const 분류 = $('nkind');
  const 분류값 = () => 분류.querySelector('button.on').dataset.v;
  분류.onclick = e => {
    const b = e.target.closest('button[data-v]');
    if (!b) return;
    분류.querySelectorAll('button').forEach(x => {
      x.classList.toggle('on', x === b);
      x.setAttribute('aria-pressed', String(x === b));
    });
    $('parentField').hidden = b.dataset.v !== 'sub';
    켠다($('nerrparent'), false);
  };

  /* 상위 업무는 가나다순으로 늘어놓고, 이름으로 좁혀 찾는다 */
  const PARENTS = JSON.parse(root.querySelector('#parents-data').textContent)
    .slice().sort((a, b) => a.title.localeCompare(b.title, 'ko'));
  function 상위를그린다() {
    const q = $('nparentSearch').value.trim().toLowerCase();
    const 두고 = $('nparent').value;
    const rows = PARENTS.filter(p => !q || p.title.toLowerCase().includes(q));
    /* 첫 줄은 고르지 않은 자리다 — 비워 두면 첫 업무가 골라진 채로 저장된다 */
    $('nparent').innerHTML = '<option value="">— Main 업무 고르기 —</option>' + rows
      .map(p => `<option value="${p.library_id}">${esc(p.title)}</option>`).join('');
    if (rows.some(p => String(p.library_id) === 두고)) $('nparent').value = 두고;
    $('nparentCount').textContent = q
      ? `${rows.length}건 / 전체 ${PARENTS.length}건`
      : `전체 ${PARENTS.length}건`;
  }
  $('nparentSearch').oninput = 상위를그린다;
  상위를그린다();

  /* ── 기간 — 드로어(4-9)와 **같은 부품**. 여기서는 화면만 고치고 서버로 안 보낸다 ── */
  const 날짜 = $('ndates'), 달력 = $('ncalbtn');
  달력.onclick = () => {
    if (!window.DatePick) return;
    달력.classList.add('on');
    window.DatePick.open(달력, {
      start: 날짜.dataset.start || '', end: 날짜.dataset.end || 날짜.dataset.start || '',
      onSave: (s, e) => {
        날짜.dataset.start = s; 날짜.dataset.end = e || s;
        날짜.textContent = 날짜글(s, e);
        켠다($('nerrsave'), false);
        return true;
      },
    });
    const 지켜본다 = setInterval(() => {
      if (!window.DatePick.isOpen()) { 달력.classList.remove('on'); clearInterval(지켜본다); }
    }, 200);
  };

  /* ── 새 업무 만들기 ── */
  $('addNew').onclick = async () => {
    const title = $('ntitle').value.trim();
    const kind = 분류값();
    const 상위 = kind === 'sub' ? $('nparent').value : '';
    /* 까닭은 **틀린 칸 바로 아래**에 적는다 — 멀리 적으면 어느 칸이 틀렸는지 모른다 (4-9) */
    켠다($('nerrtitle'), !title);
    켠다($('nerrparent'), kind === 'sub' && !상위);
    켠다($('nerrsave'), false);
    if (!title) { $('ntitle').focus(); return; }
    if (kind === 'sub' && !상위) { $('nparent').focus(); return; }

    const res = await fetch('/board/add/new', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title,
        department_key: $('ndept').value,
        kind,
        /* **안 고르면 안 보낸다** — 빈 글자를 보내면 서버가 「꼴이 틀린 값」 으로
           읽는다. 안 고른 것은 잘못 고른 것이 아니고, 그렇게 만든 업무는
           달력이 「날짜가 없는 업무」 로 따로 모아 둔다 (4-13) */
        start: 날짜.dataset.start || null,
        end: 날짜.dataset.end || null,
        parent_library_id: 상위 ? Number(상위) : null,
      }),
    });
    if (!res.ok) {
      /* **기간을 안 고른 것은 이제 여기로 안 온다**(2026-09-25) — 날짜 없는
         업무로 만들어진다. 여기 오는 것은 꼴이 틀린 값과 마감이 시작보다
         앞선 값이고, 무엇이 틀렸는지는 서버가 말한다 — 같은 말을 화면에도
         적어 두면 두 벌이 되어 한쪽만 고쳐진다 */
      /* **`detail` 이 늘 글자는 아니다** — 입력 꼴이 안 맞으면 서버가 422 와
         함께 **목록**을 낸다. 그대로 넣으면 `켠다` 가 글자가 아닌 값을 받아
         **빈 줄이 뜬 채로 아무 말도 안 하게** 된다(실제로 그랬다 · 5-0 의
         「조용히 삼키지 않는다」). 글자가 아니면 우리 말로 바꾼다. */
      const 까닭 = (await res.json().catch(() => ({}))).detail;
      켠다($('nerrsave'), typeof 까닭 === 'string' && 까닭 ? 까닭 : '만들지 못했습니다.');
      return;
    }
    await res.json();
    간다();
  };
}

/* ─────────────────────────── 팝업 껍데기 ─────────────────────────── */

function 자리를잡는다(el, left, top) {
  const w = el.offsetWidth;
  const 왼쪽 = Math.min(Math.max(left, Math.min(남길가로 - w, 0)), Math.max(innerWidth - 남길가로, 0));
  const 위쪽 = Math.min(Math.max(top, 0), Math.max(innerHeight - 윗줄, 0));
  el.style.left = 왼쪽 + 'px';
  el.style.top = 위쪽 + 'px';
  return {왼쪽, 위쪽};
}

function 끌게한다(el, bar) {
  bar.addEventListener('pointerdown', e => {
    if (e.button !== 0 || e.target.closest('.apx')) return;   // × 는 끌기에서 뺀다
    const dx = e.clientX - el.offsetLeft, dy = e.clientY - el.offsetTop;
    bar.setPointerCapture(e.pointerId);
    const 옮긴다 = ev => 자리를잡는다(el, ev.clientX - dx, ev.clientY - dy);
    const 끝 = () => {
      bar.removeEventListener('pointermove', 옮긴다);
      bar.removeEventListener('pointerup', 끝);
      bar.removeEventListener('pointercancel', 끝);
    };
    bar.addEventListener('pointermove', 옮긴다);
    bar.addEventListener('pointerup', 끝);
    bar.addEventListener('pointercancel', 끝);
    e.preventDefault();
  });
}

function 닫는다() {
  if (!팝업) return;
  팝업.remove();
  팝업 = null;
  if (되돌릴초점 && document.contains(되돌릴초점)) 되돌릴초점.focus();
  되돌릴초점 = null;
}

async function 연다(opts) {
  const {부제 = '', start = '', onSaved} = opts || {};
  닫는다();
  window.DatePick?.close();          // 다른 팝업이 떠 있으면 먼저 닫는다
  되돌릴초점 = document.activeElement;

  const el = document.createElement('div');
  el.className = 'addpop';
  el.id = 'addpop';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', '업무 추가');
  el.innerHTML =
    `<div class="apbar"><b>업무 추가</b><span class="apsub">${esc(부제)}</span>` +
    `<button type="button" class="apx" aria-label="닫기">×</button></div>` +
    `<div class="apbody apwait">불러오는 중…</div>`;
  document.body.appendChild(el);
  팝업 = el;
  자리를잡는다(el, (innerWidth - el.offsetWidth) / 2, 첫위);
  끌게한다(el, el.querySelector('.apbar'));
  el.querySelector('.apx').onclick = 닫는다;

  let html;
  try {
    const res = await fetch('/board/add/form', {headers: {'X-Requested-With': 'fetch'}});
    if (!res.ok) throw new Error(res.status);
    html = await res.text();
  } catch (err) {
    /* 조용히 삼키지 않는다 — 안 뜬 채로 두면 눌렀는데 아무 일이 없는 것이 된다 (5-0) */
    if (팝업 === el) el.querySelector('.apbody').textContent = '업무 추가를 불러오지 못했습니다. 다시 눌러 주세요.';
    return;
  }
  if (팝업 !== el) return;            // 받는 동안 닫혔다
  el.querySelector('.apbody').outerHTML = html;
  const root = el.querySelector('[data-add-root]');
  if (start) {
    const 날짜 = root.querySelector('#ndates');
    날짜.dataset.start = 날짜.dataset.end = start;
    날짜.textContent = 날짜글(start, start);
  }
  살린다(root, () => { 닫는다(); (onSaved || (() => location.reload()))(); });
  /* 몸통이 들어와 높이가 늘었다 — **아래가 화면 밖으로 나가면 위로 올린다.**
     목업의 「위 70px」 과 「최대 높이 = 화면 − 40」 은 낮은 창에서 함께 성립하지
     않는다(70 + (높이−40) 이 화면을 넘는다). 들어가면 70 을 그대로 쓰고,
     안 들어갈 때만 올린다 — 끌기 범위(윗줄만 남기면 된다)는 그대로다. */
  자리를잡는다(el, el.offsetLeft,
    Math.min(el.offsetTop, Math.max(0, innerHeight - el.offsetHeight - 20)));
  root.querySelector('#ntitle')?.focus();
}

/* Esc — **기간 달력이 떠 있으면 그쪽 차례다.** 둘 다 window 에서 받는데 아무도
   전파를 안 막으면 달력을 닫으려고 누른 Esc 에 팝업까지 닫혀 **적던 이름이
   사라진다**(드로어도 함께 닫힌다). 닫을 때는 뒤로 안 넘긴다. */
addEventListener('keydown', e => {
  if (e.key !== 'Escape' || !팝업) return;
  if (window.DatePick && window.DatePick.isOpen()) return;
  e.stopPropagation();
  닫는다();
});

/* 저장한 뒤에 **화면을 옮기지 않는다** — 지금 화면을 그 자리에서 새로 고친다.
   달력은 보던 달·범위를 잃지 않으려고 `다시그린다` 를 스스로 끼운다(calendar.js). */
window.업무추가 = {open: 연다, close: 닫는다, isOpen: () => !!팝업, 다시그린다: null};

/* 여는 자리는 보드의 「+ 업무 추가」 와 달력 날짜 칸의 「+」 다 — 위임으로 받는다.
   달 격자는 통째로 갈아 끼워지므로(4-13) 칸마다 걸면 달을 넘긴 뒤에 죽는다. */
document.addEventListener('click', e => {
  const b = e.target instanceof Element && e.target.closest('[data-addpop]');
  if (!b) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;   // 새 탭은 막지 않는다
  e.preventDefault();
  연다({
    부제: b.dataset.addpopSub || '',
    start: b.dataset.addpopDate || '',
    onSaved: () => {
      /* 달력은 격자만 갈아 끼워 보던 달을 지킨다 — **그 파일에는 `location.reload`
         가 없어야 한다**(4-13 을 지키는 시험 둘이 그 낱말을 본다). 못 그렸다고
         답하면 여기서 페이지를 다시 그린다. */
      const 그린다 = window.업무추가.다시그린다;
      if (!그린다 || 그린다() === false) location.reload();
    },
  });
});

/* 옛 화면(`/board/add`)은 그 자리에 폼이 이미 그려져 있다 */
document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-add-root]');
  if (root && !팝업) 살린다(root, null);
});
})();
