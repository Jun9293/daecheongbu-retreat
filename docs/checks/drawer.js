/* 상세 패널 상호작용 점검 — CLAUDE.md 10장의 규칙을 실제로 돌리는 스크립트.
 *
 * 쓰는 법: 보드(/board)를 연 뒤 브라우저 콘솔에 이 파일 내용을 붙여넣습니다.
 * 화면을 고쳤으면 "됐다"고 말하기 전에 이걸 돌립니다.
 *
 * 무엇을 보는가 — 각 조작이 '되는가'만이 아니라, 그 뒤에도 주변이 그대로인가.
 *   · 드로어가 열려 있는가 (패널 안의 버튼은 패널을 닫지 않는다)
 *   · 부서 그룹이 펼쳐진 채인가 (보던 자리를 잃지 않는다)
 *   · 스크롤이 그대로인가 (이동은 명시적으로 요청했을 때만)
 * 보임/숨김은 속성이 아니라 offsetParent 로 판정한다 — el.hidden 은 거짓말을 한다.
 */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const $ = id => document.getElementById(id);
  const sheet = $('sheet'), board = $('board'), dw = $('drawer');
  const shown = el => !!(el && el.offsetParent);
  const errors = [], results = [];

  const snapshot = () => ({
    drawer: dw.classList.contains('open'),
    teams: [...sheet.querySelectorAll('.row.team')].filter(t => !t.classList.contains('collapsed')).length,
    scroll: Math.round(board.scrollTop),
  });

  const check = async (label, act, opts = {}) => {
    const before = snapshot();
    await act();
    await sleep(opts.wait || 420);
    const after = snapshot();
    const bad = [];
    if (!opts.mayClose && before.drawer && !after.drawer) bad.push('드로어가 닫힘');
    if (!opts.mayCollapse && after.teams < before.teams) bad.push('부서 그룹이 접힘');
    if (!opts.mayScroll && Math.abs(after.scroll - before.scroll) > 4) bad.push('스크롤이 움직임');
    if (bad.length) errors.push(label + ' → ' + bad.join(', '));
    results.push(`${bad.length ? '✗' : '✓'} ${label}`);
  };

  $('me').value = 'all'; $('me').dispatchEvent(new Event('change'));
  await sleep(500);
  board.scrollTop = 220; await sleep(200);
  const bar = [...sheet.querySelectorAll('.bar[data-run]')].find(b => shown(b) && !b.dataset.ghost);
  bar.click(); await sleep(800);
  if (!dw.classList.contains('open')) return {치명: '드로어가 열리지 않음'};

  results.push((shown($('daddlog')) ? '✓' : '✗') + ' 논의 입력칸이 화면에 보임');
  if (!shown($('daddlog'))) errors.push('논의 입력칸이 보이지 않음');

  await check('탭 — 달력', () => $('dtabs').querySelector('[data-p="cal"]').click());
  await check('탭 — 연결된 업무', () => $('dtabs').querySelector('[data-p="rel"]').click());
  await check('탭 — 논의 내역', () => $('dtabs').querySelector('[data-p="log"]').click());
  await check('상태 배지 열기', () => $('statchip').click());
  await check('상태 배지 다시 눌러 닫기', () => $('statchip').click());
  await check('담당자 드롭다운', () => $('dassignee').click());
  await check('담당팀 드롭다운', () => $('ddept').click());
  await check('시작일 칸', () => $('dstart').click());
  await check('논의 입력칸', () => $('dbody').click());
  await check('대체 체크박스', () => $('dsuper').click());
  await check('대체 체크박스 해제', () => $('dsuper').click());
  await check('논의 취소 버튼', () => $('dcancelnew').click());

  const pen = document.querySelector('#dlog .editline');
  if (pen) {
    await check('논의 수정 열기', () => pen.click());
    const box = document.querySelector('#dlog textarea.editbox');
    results.push((box ? '✓' : '✗') + ' 편집창이 열림');
    if (!box) errors.push('편집창이 열리지 않음');
    if (box) {
      await check('편집창 안 클릭', () => box.click());
      await check('편집 취소', () => document.querySelector('#dlog [data-cancel-edit]').click());
    }
  } else results.push('· 고칠 수 있는 논의가 없어 수정은 건너뜀');

  $('dtabs').querySelector('[data-p="rel"]').click(); await sleep(250);
  const rb = document.querySelector('#drel .rb');
  if (rb) {
    await check('연결된 업무 항목', () => rb.click());
    await check('연결 메뉴 다시 눌러 닫기', () => rb.click());
  }

  // 반대편도 확인 — 규칙이 과하게 걸려 정작 닫혀야 할 때 안 닫히면 안 된다
  const bb = board.getBoundingClientRect();
  const lane = [...sheet.querySelectorAll('.lane')]
    .filter(l => { const r = l.getBoundingClientRect();
      return r.top > bb.top + 60 && r.bottom < bb.bottom - 10; })
    .slice(-1)[0];
  if (lane) {
    const lr = lane.getBoundingClientRect();
    const x = Math.round(Math.min(lr.right - 20, bb.right - 40));
    const y = Math.round(lr.top + lr.height / 2);
    await check('보드 빈 영역 클릭', () => {
      const el = document.elementFromPoint(x, y);
      ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t =>
        el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, clientX:x, clientY:y, view:window})));
    }, {mayClose: true});
    const closed = !dw.classList.contains('open');
    results.push((closed ? '✓' : '✗') + ' 빈 영역 클릭으로는 닫힌다');
    if (!closed) errors.push('빈 영역 클릭으로 닫히지 않음');
  }

  console.table(results);
  return {통과: errors.length === 0, 실패: errors, 항목: results};
})()
