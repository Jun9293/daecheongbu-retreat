/* 목록 보기 (CLAUDE.md 4-14) — 행을 펼치면 **보드와 같은 패널**이 그 자리에서 열린다.
 *
 * 패널은 한 벌이다: 화면 partials/drawer.html · 코드 drawer.js. 여기는
 * "목록은 이렇게 고쳐 그린다" 만 알려 준다 — 패널을 눌린 행 아래로 옮기고,
 * 상태가 바뀌면 그 행의 배지를 다시 칠한다. 논의·첨부·선후행·진단은 전부
 * drawer.js 가 보드와 같은 주소(/board/task/…)로 다닌다. 목록 전용 상세를
 * 만들면 두 곳에서 갈리고, 갈린 쪽을 아무도 눈치채지 못한다.
 */
(function () {
'use strict';

const list = document.getElementById('tlist');
const dw = document.getElementById('drawer');
if (!list || !dw) return;

const slotOf = id => document.querySelector(`.lslot[data-slot="${CSS.escape(String(id))}"]`);
const rowOf = id => document.querySelector(`.trow[data-run="${CSS.escape(String(id))}"]`);

/* 펼친 상태는 주소에 남는다 (4-14) — ?task=<run_id>. 보드·달력과 같은 이름이라
   알림의 바로가기가 목록으로 와도 같은 것이 열린다. */
function writeUrl(runId) {
  const q = new URLSearchParams(location.search);
  if (runId == null) q.delete('task');
  else q.set('task', String(runId));
  const qs = q.toString();
  history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
}

/* 패널을 눌린 행 아래로 옮긴다 — "그 자리에서 펼쳐진다" (4-14).
   행이 화면에 없으면(필터에 걸렸거나 다른 회차) 옮기지 않고 오른쪽
   패널 그대로 연다 — 알림으로 들어온 업무를 못 여는 것보다 낫다. */
function place(runId) {
  document.querySelectorAll('.lslot').forEach(s => {
    if (s.dataset.slot !== String(runId)) s.hidden = true;
  });
  carets(runId);
  const slot = slotOf(runId);
  if (!slot) { dw.classList.remove('inline'); document.body.appendChild(dw); return; }
  const done = slot.closest('details.ldone');
  if (done) done.open = true;            // 완료 접힘 안이면 먼저 편다
  slot.hidden = false;
  slot.appendChild(dw);
  dw.classList.add('inline');
}

/* ▸/▾ — 접었다 펴는 것임이 보이게 (4-14). 펼쳐진 행의 캐럿만 ▾ 다. */
function carets(openId) {
  document.querySelectorAll('.lfoot').forEach(f => {
    const on = openId != null && f.dataset.run === String(openId);
    f.classList.toggle('open', on);
    const c = f.querySelector('.caret');
    if (c) c.textContent = on ? '▾' : '▸';
  });
}

Drawer.init({
  canGoTo: false,                        // 목록에는 스크롤해서 갈 다른 자리가 없다
  meta(runId) {
    const row = rowOf(runId);
    const nm = row && row.querySelector('.nm');
    // 행이 없어도 연다 — 제목만 잠깐 비고 서버에서 받아 채운다 (달력과 같다)
    return {title: nm ? nm.childNodes[0].textContent.trim() : ''};
  },
  onOpen(runId) { place(runId); writeUrl(runId); },
  onClose() {
    document.querySelectorAll('.lslot').forEach(s => { s.hidden = true; });
    carets(null);
    writeUrl(null);
  },
  /* 제목을 고치면 행의 제목도 따라 바뀐다 — 번호는 그대로다 (4-14) */
  onTitle(runId, title) {
    const row = rowOf(runId);
    const nm = row && row.querySelector('.nm');
    if (!nm) return;
    const no = nm.querySelector('.runno');
    nm.textContent = title;
    if (no) nm.prepend(no);
  },
  /* ?task= 로 들어오면 그 행이 펼쳐진 채 스크롤까지 (4-14). 스크롤은 여기서만 —
     행을 눌러 여는 것은 그 자리에서 보는 동작이라 화면을 움직이지 않는다. */
  openFromUrl(runId) {
    Drawer.open(runId);
    const row = rowOf(runId);
    if (row) setTimeout(() => row.scrollIntoView({block: 'center'}), 0);
  },
  /* 상태가 바뀌면 그 행의 배지를 서버가 준 값으로 다시 칠한다 (board.paint_of).
     화면이 다시 계산하면 두 벌이 된다. */
  onStatus(runId, view) {
    const row = rowOf(runId);
    if (!row || !view.badge) return;
    const badge = row.querySelector('.stbadge');
    if (badge) {
      badge.className = 'stbadge ' + view.badge.cls;
      badge.textContent = view.badge.label;
    }
    const due = row.querySelector('.cell.due');
    if (due) due.className = due.className.replace(/b-\S+/, 'b-' + view.badge.cls);
  },
  isTaskClick: el => el.closest('.lopen'),

  /* ── 일부러 등록하지 않은 것 ──────────────────────────────────────
     빠뜨린 것과 구별되도록 적는다. call() 은 없는 핸들러를 조용히 건너뛴다. */
  __unusedFor: 'af295bbc',
  __unused: {
    goTo: '목록에는 스크롤해서 갈 다른 자리가 없다. canGoTo:false 라 불리지도 않는다',
    link: '연결 강조는 보드의 바 사이에 선을 긋는 것이다. 목록 행에는 그을 선이 없다',
    afterLayout: '패널이 행 아래로 들어가므로 폭이 바뀌어도 다시 그릴 것이 없다',
    onDates: '행에 실린 마감은 서버가 그린 것이고, 날짜를 고치면 정렬 자리도 달라진다 — 다음에 열 때 서버가 다시 그린다',
    onAssignee: '행의 담당자도 같다 — 페이지를 다시 그릴 때 서버가 채운다',
    onDepartment: '담당팀을 옮기면 행이 다른 부서 것이 된다 — 통째로 다시 그리는 것이 맞다. 기본값(새로고침)을 쓴다',
  },
  // 목록 행은 관련팀을 그리지 않는다 — true 는 새로고침을 막으려는 것뿐이다
  onRelatedTeams() { return true; },
});

/* 「상세 · 선행 작업 · 확인 요청」 — 눌린 행 아래에서, 그 탭을 연 채로
   펼쳐진다 (4-14). 같은 행의 같은 글자를 다시 누르면 닫는다. */
let lastTab = null;
list.addEventListener('click', e => {
  const btn = e.target.closest('.lopen');
  if (!btn) return;
  const runId = btn.dataset.open;
  const tab = btn.dataset.tab || 'rules';
  const sameRun = Drawer.isOpen() && String(Drawer.current()) === String(runId);
  if (sameRun && lastTab === tab) { Drawer.close(); lastTab = null; return; }
  if (sameRun) { Drawer.selectTab(tab); lastTab = tab; return; }
  Drawer.open(runId);
  Drawer.selectTab(tab);
  lastTab = tab;
});
})();
