/* 상세 패널 상호작용 점검 — CLAUDE.md 10장의 규칙을 실제로 돌리는 스크립트.
 *
 * 쓰는 법: 보드(/board)를 연 뒤 브라우저 콘솔에 이 파일 내용을 붙여넣습니다.
 * 화면을 고쳤으면 "됐다"고 말하기 전에 이걸 돌립니다.
 *
 * 탭이 화면에 보이는 상태에서 돌립니다. 배경 탭에서는 브라우저가 타이머를
 * 1초 단위로 묶어 버려 중간에 끊깁니다 — 페이지가 멈춘 것이 아닙니다.
 *
 * 2026-08-31 UI 를 노션 방향으로 옮기면서 다시 돌렸습니다. **기존 26항목은 선택자를
 * 하나도 고치지 않고 그대로 통과했습니다** — 상단 탭 줄을 없애고 사이드바를 붙이고
 * 색·여백을 바꾼 것이 상세 패널의 조작에는 닿지 않았기 때문입니다. 규칙이 맞지
 * 않게 된 항목은 없어서 지우거나 바꾼 것도 없습니다.
 * 대신 새로 생긴 자리(첨부파일 탭 · 사이드바)를 같은 기준으로 덮도록 항목을 더했습니다.
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

  results.push((document.querySelector('#dtabs [aria-selected=true]').dataset.p === 'rules' ? '✓' : '✗')
    + ' 처음 열면 업무 규칙 탭');

  await check('탭 — 논의 내역', () => $('dtabs').querySelector('[data-p="log"]').click());
  results.push((shown($('daddlog')) ? '✓' : '✗') + ' 논의 입력칸이 화면에 보임');
  if (!shown($('daddlog'))) errors.push('논의 입력칸이 보이지 않음');

  await check('탭 — 업무 규칙', () => $('dtabs').querySelector('[data-p="rules"]').click());
  if ($('drulesopen')) {
    await check('규칙 편집 열기', () => $('drulesopen').click());
    results.push((shown($('drulesedit')) ? '✓' : '✗') + ' 규칙 편집창이 보임');
    if (!shown($('drulesedit'))) errors.push('규칙 편집창이 보이지 않음');
    await check('규칙 편집 취소', () => $('drulescancel').click());
  }
  await check('탭 — 달력', () => $('dtabs').querySelector('[data-p="cal"]').click());
  await check('탭 — 연결된 업무', () => $('dtabs').querySelector('[data-p="rel"]').click());

  // 첨부파일 — 회차별. 탭을 옮기는 것도 '패널 안의 조작'이라 같은 기준으로 본다.
  await check('탭 — 첨부파일', () => $('dtabs').querySelector('[data-p="files"]').click());
  results.push((shown($('p-files')) ? '✓' : '✗') + ' 첨부파일 탭이 화면에 보임');
  if (!shown($('p-files'))) errors.push('첨부파일 탭이 보이지 않음');
  {
    const tabs = [...document.querySelectorAll('#dtabs button')].map(b => b.dataset.p);
    const last = tabs[tabs.length - 1] === 'files';
    results.push((last ? '✓' : '✗') + ` 첨부파일이 탭 맨 끝 (${tabs.join(' · ')})`);
    if (!last) errors.push('첨부파일 탭이 맨 끝이 아님');
    // 올리는 자리는 탭 안에 있다. 고칠 수 없는 업무라면 없는 것이 맞다.
    const canEdit = !document.querySelector('#statchip[disabled]');
    const drop = shown($('ddrop'));
    const ok = canEdit ? drop : !drop;
    results.push((ok ? '✓' : '✗') + ` 끌어다 놓는 자리 (편집 ${canEdit ? '가능' : '불가'})`);
    if (!ok) errors.push('올리는 자리가 권한과 어긋남');
    // 같은 기능이 두 군데 있으면 안 된다 — 하단의 '파일 첨부' 버튼은 없앴다
    const foot = [...document.querySelectorAll('.dfoot button')].map(b => b.textContent.trim());
    const clean = !foot.some(t => t.includes('파일 첨부'));
    results.push((clean ? '✓' : '✗') + ` 하단에 '파일 첨부' 버튼 없음 (${foot.join(', ') || '없음'})`);
    if (!clean) errors.push("하단에 '파일 첨부' 버튼이 남아 있음");
  }
  await check('첨부파일 — 올리는 자리 클릭', () => { const d = $('ddrop'); if (d && shown(d)) d.click(); });
  await check('탭 — 논의 내역 (되돌아오기)', () => $('dtabs').querySelector('[data-p="log"]').click());
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
  } else results.push('· 이 업무에는 연결된 업무가 없어 건너뜀');

  // 선행 고르기 — fixed 요소라 offsetParent 가 null 이다. 그려진 크기로 판정한다.
  if ($('preedit')) {
    const painted = el => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
      return cs.display !== 'none' && r.width > 0 && r.height > 0; };
    await check('선행 고르기 열기', () => $('preedit').click());
    results.push((painted($('prepick')) ? '✓' : '✗') + ' 선행 고르기 판이 보임');
    if (!painted($('prepick'))) errors.push('선행 고르기 판이 보이지 않음');
    await check('선행 고르기 닫기', () => document.querySelector('#prepick [data-close]').click());
  }

  // 진단 패널 — 하단 고정이므로 드로어를 밀어내거나 가리면 안 된다
  {
    const painted = el => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
      return cs.display !== 'none' && r.width > 0 && r.height > 0; };
    results.push((painted($('diag')) ? '✓' : '✗') + ' 진단 패널이 하단에 그려짐');
    if (!painted($('diag'))) errors.push('진단 패널이 보이지 않음');
    await check('진단 다시 분석', () => $('dgR').click(), {wait: 900});
    results.push(($('dgTtl').textContent.trim() ? '✓' : '✗')
      + ` 다시 분석 뒤 판정 유지 (${$('dgTtl').textContent.trim()})`);
  }

  // 반대편도 확인 — 규칙이 과하게 걸려 정작 닫혀야 할 때 안 닫히면 안 된다.
  // 진짜 빈 점을 찾아야 한다. 고스트 바도 바이므로, 눌러도 닫히지 않는 게 정상이다.
  const bb = board.getBoundingClientRect();
  const empty = (() => {
    for (const l of sheet.querySelectorAll('.lane')) {
      const r = l.getBoundingClientRect();
      if (r.top < bb.top + 60 || r.bottom > bb.bottom - 10) continue;
      const y = Math.round(r.top + r.height / 2);
      for (let x = Math.round(Math.min(r.right, bb.right) - 20); x > bb.left + 220; x -= 12) {
        const el = document.elementFromPoint(x, y);
        if (!el || el.closest('#drawer')) continue;
        if (el.closest('.bar[data-run]') || el.closest('[data-go]')) continue;
        if (!el.closest('.board')) continue;
        return {x, y};
      }
    }
    return null;
  })();
  if (empty) {
    const {x, y} = empty;
    await check('보드 빈 영역 클릭', () => {
      const el = document.elementFromPoint(x, y);
      ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t =>
        el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, clientX:x, clientY:y, view:window})));
    }, {mayClose: true});
    const closed = !dw.classList.contains('open');
    results.push((closed ? '✓' : '✗') + ' 빈 영역 클릭으로는 닫힌다');
    if (!closed) errors.push('빈 영역 클릭으로 닫히지 않음');
  } else results.push('· 화면 안에 빈 칸이 없어 건너뜀');

  // 달력은 드로어를 넓혀도 커지지 않아야 한다 — 한 화면에 들어와야 하므로
  $('dtabs').querySelector('[data-p="cal"]').click();
  await sleep(250);
  const cellW = () => { const c = document.querySelector('.cal .dcell:not(.pad)');
    return c ? Math.round(c.getBoundingClientRect().width) : 0; };
  const narrow = cellW();
  document.documentElement.style.setProperty('--dw', '760px'); await sleep(250);
  const wide = cellW();
  document.documentElement.style.setProperty('--dw', '400px'); await sleep(200);
  results.push((narrow === wide ? '✓' : '✗') + ` 달력 칸 크기 고정 (${narrow}px → ${wide}px)`);
  if (narrow !== wide) errors.push('드로어를 넓히면 달력이 커진다');

  // ── 사이드바 — 상단 탭 줄을 없앤 자리. 기본은 접힘이고 여는 길이 둘이다.
  //    화면 이동 수단이 여기 하나뿐이라, 드로어를 연 채로도 열려야 한다.
  {
    const nav = document.getElementById('sidenav');
    const edge = document.getElementById('sideedge');
    const toggle = document.getElementById('sidetoggle');
    // 미끄러지는 동안을 재지 않는다. 탭이 가려져 있으면 브라우저가 그리기를
    // 멈춰 전환이 진행되지 않고, 그러면 "안 열렸다"고 잘못 말한다 — 화면이
    // 틀린 게 아니라 재는 방법이 틀린 것이다. 여기서만 전환을 끄고 끝나면 되돌린다.
    const navEase = nav.style.transition, bodyEase = document.body.style.transition;
    nav.style.transition = 'none';
    document.body.style.transition = 'none';
    const at = () => Math.round(nav.getBoundingClientRect().left);
    const pinned = () => document.body.classList.contains('sidepin');
    const wasPinned = pinned();
    if (wasPinned) { toggle.click(); await sleep(80); }

    results.push((at() < 0 ? '✓' : '✗') + ` 사이드바가 접힌 채로 시작 (left ${at()}px)`);
    if (at() >= 0) errors.push('사이드바가 접혀 있지 않음');

    results.push((!document.querySelector('nav.tabs') ? '✓' : '✗') + ' 상단 탭 줄이 없음');
    if (document.querySelector('nav.tabs')) errors.push('상단 탭 줄이 남아 있음');

    // 가장자리 호버 — 잠깐 들춰 본다. 본문은 밀리지 않는다.
    await check('사이드바 — 가장자리 호버', async () => {
      edge.dispatchEvent(new MouseEvent('mouseenter', {bubbles: false}));
    }, {wait: 120});
    const peeked = at() === 0 && getComputedStyle(document.body).paddingLeft === '0px';
    results.push((peeked ? '✓' : '✗') + ' 가장자리 호버로 잠깐 열리고 본문은 그대로');
    if (!peeked) errors.push('가장자리 호버가 동작하지 않음');
    nav.dispatchEvent(new MouseEvent('mouseleave', {bubbles: false}));
    await sleep(260);

    // 토글 — 고정해서 연다. 본문이 그만큼 밀린다.
    await check('사이드바 — 토글로 고정', () => toggle.click(), {wait: 120, mayScroll: true});
    const pin = pinned() && at() === 0
      && parseInt(getComputedStyle(document.body).paddingLeft, 10) > 100;
    results.push((pin ? '✓' : '✗') + ' 토글로 고정하면 본문이 밀린다');
    if (!pin) errors.push('토글 고정이 동작하지 않음');
    await check('사이드바 — 토글로 접기', () => toggle.click(), {wait: 120, mayScroll: true});
    if (wasPinned) { toggle.click(); await sleep(80); }
    nav.style.transition = navEase;
    document.body.style.transition = bodyEase;
  }

  // ── 가로 격자선을 넣지 않는다 (CLAUDE.md 4장 UI 방향).
  //    세로선은 남기므로 '선이 하나도 없다'가 아니라 '가로선만 없다'를 본다.
  {
    const rows = [...sheet.querySelectorAll('.row.main .lane, .row.sub .lane')].filter(shown);
    const lined = rows.filter(el => {
      const cs = getComputedStyle(el);
      return cs.borderBottomWidth !== '0px' && cs.borderBottomStyle !== 'none';
    });
    results.push((lined.length === 0 ? '✓' : '✗') + ` 가로 격자선 없음 (${lined.length}줄)`);
    if (lined.length) errors.push('행에 가로선이 남아 있음');
    const vert = [...sheet.querySelectorAll('.gridlines i')].length;
    results.push((vert > 0 ? '✓' : '✗') + ` 세로 격자선은 남아 있음 (${vert}개)`);
    if (!vert) errors.push('세로 격자선이 사라짐');
  }

  console.table(results);
  return {통과: errors.length === 0, 실패: errors, 항목: results};
})()
