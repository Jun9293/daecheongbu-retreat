/* 상세 패널 상호작용 점검 — CLAUDE.md 10장의 규칙을 실제로 돌리는 스크립트.
 *
 * 쓰는 법: **보드(/board) 또는 달력(/calendar)** 을 연 뒤 브라우저 콘솔에
 * 이 파일 내용을 붙여넣습니다. 화면을 고쳤으면 "됐다"고 말하기 전에 돌립니다.
 *
 * **두 화면에서 각각 돌립니다.** 패널은 한 벌이지만(templates/partials/drawer.html ·
 * static/js/drawer.js), 그것을 여는 자리와 고쳐 그리는 코드는 화면마다 다릅니다.
 * 한쪽만 통과하면 패널이 실제로는 한 벌이 아니라는 뜻입니다 (CLAUDE.md 4-13).
 *
 * 탭이 화면에 보이는 상태에서 돌립니다. 배경 탭에서는 브라우저가 타이머를
 * 1초 단위로 묶어 버려 중간에 끊깁니다 — 페이지가 멈춘 것이 아닙니다.
 *
 * 무엇을 보는가 — 각 조작이 '되는가'만이 아니라, 그 뒤에도 주변이 그대로인가.
 *   · 드로어가 열려 있는가 (패널 안의 버튼은 패널을 닫지 않는다)
 *   · 보던 자리가 그대로인가 (보드는 부서 그룹, 달력은 보던 달과 칩)
 *   · 스크롤이 그대로인가 (이동은 명시적으로 요청했을 때만)
 * 보임/숨김은 속성이 아니라 offsetParent 로 판정한다 — el.hidden 은 거짓말을 한다.
 */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const $ = id => document.getElementById(id);
  const dw = $('drawer');
  const shown = el => !!(el && el.offsetParent);
  const painted = el => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== 'none' && r.width > 0 && r.height > 0; };
  const errors = [], results = [];

  if (!dw) return {치명: '이 화면에는 상세 패널이 없습니다 (/board 나 /calendar 에서 돌리세요)'};

  /* ── 어느 화면인가 ────────────────────────────────────────────────
     패널은 같지만 "무엇을 눌러 여는가" 와 "보던 자리가 무엇인가" 는 다르다.
     보드는 바와 부서 그룹, 달력은 점과 보던 달이다. */
  const sheet = $('sheet'), board = $('board');
  const calbar = document.querySelector('.calbar');
  const isBoard = !!(sheet && board);
  const where = isBoard ? '보드' : '달력';
  const scroller = isBoard ? board
    : (document.querySelector('.calwrap') || document.scrollingElement);

  const openers = () => isBoard
    ? [...sheet.querySelectorAll('.bar[data-run]')].filter(b => shown(b) && !b.dataset.ghost)
    : [...document.querySelectorAll('.cal-dot[data-run]')].filter(shown);

  const snapshot = () => ({
    drawer: dw.classList.contains('open'),
    // 보던 자리 — 보드는 펼쳐진 부서 수, 달력은 보이는 점의 수
    kept: isBoard
      ? [...sheet.querySelectorAll('.row.team')].filter(t => !t.classList.contains('collapsed')).length
      : openers().length,
    scroll: Math.round(scroller.scrollTop),
    // 달력은 보던 달과 칩이 그대로여야 한다
    month: calbar ? calbar.dataset.month : '',
    chips: calbar ? calbar.dataset.scope + '/' + calbar.dataset.onlyOpen : '',
  });

  const check = async (label, act, opts = {}) => {
    const before = snapshot();
    await act();
    await sleep(opts.wait || 420);
    const after = snapshot();
    const bad = [];
    if (!opts.mayClose && before.drawer && !after.drawer) bad.push('드로어가 닫힘');
    if (!opts.mayCollapse && after.kept < before.kept) bad.push(isBoard ? '부서 그룹이 접힘' : '점이 사라짐');
    if (!opts.mayScroll && Math.abs(after.scroll - before.scroll) > 4) bad.push('스크롤이 움직임');
    if (after.month !== before.month) bad.push('보던 달이 바뀜');
    if (after.chips !== before.chips) bad.push('범위 칩이 바뀜');
    if (bad.length) errors.push(label + ' → ' + bad.join(', '));
    results.push(`${bad.length ? '✗' : '✓'} ${label}`);
  };

  results.push(`· 돌린 화면: ${where} (${location.pathname})`);

  // 보드는 소속 필터를 전체로 두고 시작한다. 달력에는 그 칸이 없다.
  if (isBoard) { $('me').value = 'all'; $('me').dispatchEvent(new Event('change')); await sleep(500); }
  scroller.scrollTop = isBoard ? 220 : 0;
  await sleep(200);

  const opener = openers()[0];
  if (!opener) return {치명: `${where} 에 열어 볼 업무가 하나도 없습니다`};
  opener.click();
  await sleep(900);
  if (!dw.classList.contains('open')) return {치명: `${where} 에서 드로어가 열리지 않음`};
  results.push(`✓ ${isBoard ? '바' : '점'}을 눌러 그 자리에서 패널이 열림`);

  // 달력이라면 **보드로 넘어가지 않았는지** 함께 본다 — 그것이 이 작업의 요점이다
  if (!isBoard) {
    const stayed = location.pathname.startsWith('/calendar');
    results.push((stayed ? '✓' : '✗') + ` 보드로 넘어가지 않음 (${location.pathname})`);
    if (!stayed) errors.push('점을 눌렀더니 보드로 넘어감');
  }

  results.push((document.querySelector('#dtabs [aria-selected=true]').dataset.p === 'rules' ? '✓' : '✗')
    + ' 처음 열면 업무 규칙 탭');

  await check('탭 — 논의', () => $('dtabs').querySelector('[data-p="log"]').click());
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
  await check('탭 — 연결', () => $('dtabs').querySelector('[data-p="rel"]').click());

  // 첨부파일 — 회차별. 탭을 옮기는 것도 '패널 안의 조작'이라 같은 기준으로 본다.
  await check('탭 — 첨부파일', () => $('dtabs').querySelector('[data-p="files"]').click());
  results.push((shown($('p-files')) ? '✓' : '✗') + ' 첨부파일 탭이 화면에 보임');
  if (!shown($('p-files'))) errors.push('첨부파일 탭이 보이지 않음');
  {
    const tabs = [...document.querySelectorAll('#dtabs button')].map(b => b.dataset.p);
    const last = tabs[tabs.length - 1] === 'files';
    results.push((last ? '✓' : '✗') + ` 첨부파일이 탭 맨 끝 (${tabs.join(' · ')})`);
    if (!last) errors.push('첨부파일 탭이 맨 끝이 아님');

    // 드로어 폭에서 탭 다섯이 넘치지 않는가 — **첨부파일이 잘리면 안 된다**
    const bar = $('dtabs'), fit = bar.scrollWidth <= bar.clientWidth + 1;
    const lastTab = [...bar.querySelectorAll('button')].pop();
    const inside = lastTab.getBoundingClientRect().right <= bar.getBoundingClientRect().right + 1;
    results.push((fit && inside ? '✓' : '✗')
      + ` 탭 다섯이 드로어 폭에 들어감 (${bar.scrollWidth}px / ${bar.clientWidth}px)`);
    if (!(fit && inside)) errors.push('탭이 넘쳐 첨부파일이 잘림');

    // 올리는 자리는 탭 안에 있다. 고칠 수 없는 업무라면 없는 것이 맞다.
    const canEdit = !document.querySelector('#statchip[disabled]');
    const drop = shown($('ddrop'));
    const ok = canEdit ? drop : !drop;
    results.push((ok ? '✓' : '✗') + ` 끌어다 놓는 자리 (편집 ${canEdit ? '가능' : '불가'})`);
    if (!ok) errors.push('올리는 자리가 권한과 어긋남');

    // 링크 붙이기도 같은 권한이다. 용량은 차지하지 않지만 자료인 것은 같다.
    const linkBtn = shown($('dlinkbtn'));
    const linkOk = canEdit ? linkBtn : !linkBtn;
    results.push((linkOk ? '✓' : '✗') + ` 링크 붙이기 자리 (편집 ${canEdit ? '가능' : '불가'})`);
    if (!linkOk) errors.push('링크 붙이기가 권한과 어긋남');

    // 같은 기능이 두 군데 있으면 안 된다 — 하단의 '파일 첨부' 버튼은 없앴다
    const foot = [...document.querySelectorAll('.dfoot button')].map(b => b.textContent.trim());
    const clean = !foot.some(t => t.includes('파일 첨부'));
    results.push((clean ? '✓' : '✗') + ` 하단에 '파일 첨부' 버튼 없음 (${foot.join(', ') || '없음'})`);
    if (!clean) errors.push("하단에 '파일 첨부' 버튼이 남아 있음");
  }
  await check('첨부파일 — 올리는 자리 클릭', () => { const d = $('ddrop'); if (d && shown(d)) d.click(); });

  // 링크 붙이기 — 폼을 열고, 틀린 주소를 넣어 보고, 닫는다.
  // **틀린 이유가 붙는 자리 바로 아래**에 나와야 한다.
  if (shown($('dlinkbtn'))) {
    await check('링크 붙이기 열기', () => $('dlinkbtn').click());
    results.push((shown($('dlinkform')) ? '✓' : '✗') + ' 링크 붙이기 폼이 보임');
    if (!shown($('dlinkform'))) errors.push('링크 붙이기 폼이 보이지 않음');
    await check('링크 — 주소 칸 클릭', () => $('dlinkurl').click());
    await check('링크 — 틀린 주소로 붙이기', () => {
      $('dlinkurl').value = '교개협 폴더';
      $('dlinkname').value = '';
      $('dlinksave').click();
    });
    const urlErr = shown($('dlinkurlerr')), nameErr = shown($('dlinknameerr'));
    results.push((urlErr ? '✓' : '✗') + ' 주소가 아니면 그 자리에서 말함');
    if (!urlErr) errors.push('틀린 주소를 그냥 받음');
    results.push((nameErr ? '✓' : '✗') + ' 설명을 비우면 그 자리에서 말함');
    if (!nameErr) errors.push('설명 없이 붙음');
    await check('링크 붙이기 취소', () => $('dlinkcancel').click());
    results.push((!shown($('dlinkform')) ? '✓' : '✗') + ' 취소하면 폼이 닫힘');
  } else results.push('· 고칠 수 없는 업무라 링크 붙이기는 건너뜀');

  await check('탭 — 논의 (되돌아오기)', () => $('dtabs').querySelector('[data-p="log"]').click());
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
    // '이동' 은 보드에만 뜻이 있다 — 달력에는 스크롤해서 갈 자리가 없다
    const acts = [...rb.nextElementSibling.querySelectorAll('[data-act]')].map(b => b.dataset.act);
    const want = isBoard ? 'open,move' : 'open';
    results.push((acts.join(',') === want ? '✓' : '✗')
      + ` 연결 메뉴가 화면에 맞음 (${acts.join(',') || '없음'})`);
    if (acts.join(',') !== want) errors.push(`연결 메뉴가 ${where} 에 맞지 않음`);
    await check('연결 메뉴 다시 눌러 닫기', () => rb.click());
  } else results.push('· 이 업무에는 연결된 업무가 없어 건너뜀');

  // 선행 고르기 — fixed 요소라 offsetParent 가 null 이다. 그려진 크기로 판정한다.
  if ($('preedit')) {
    await check('선행 고르기 열기', () => $('preedit').click());
    results.push((painted($('prepick')) ? '✓' : '✗') + ' 선행 고르기 판이 보임');
    if (!painted($('prepick'))) errors.push('선행 고르기 판이 보이지 않음');
    await check('선행 고르기 닫기', () => document.querySelector('#prepick [data-close]').click());
  }

  // 진단 패널 — 하단 고정이므로 드로어를 밀어내거나 가리면 안 된다
  {
    results.push((painted($('diag')) ? '✓' : '✗') + ' 진단 패널이 하단에 그려짐');
    if (!painted($('diag'))) errors.push('진단 패널이 보이지 않음');
    await check('진단 다시 분석', () => $('dgR').click(), {wait: 900});
    results.push(($('dgTtl').textContent.trim() ? '✓' : '✗')
      + ` 다시 분석 뒤 판정 유지 (${$('dgTtl').textContent.trim()})`);
  }

  // 반대편도 확인 — 규칙이 과하게 걸려 정작 닫혀야 할 때 안 닫히면 안 된다.
  // 진짜 빈 점을 찾아야 한다. 고스트 바도 바이므로, 눌러도 닫히지 않는 게 정상이다.
  const emptySpot = () => {
    const host = isBoard ? board : scroller;
    const hb = host.getBoundingClientRect();
    const cells = isBoard
      ? sheet.querySelectorAll('.lane')
      : document.querySelectorAll('.cal-cell, .calday-l');
    for (const l of cells) {
      const r = l.getBoundingClientRect();
      if (r.top < hb.top + 40 || r.bottom > hb.bottom - 10) continue;
      const y = Math.round(r.top + r.height / 2);
      for (let x = Math.round(Math.min(r.right, hb.right) - 12); x > Math.max(hb.left, r.left) + 6; x -= 10) {
        const el = document.elementFromPoint(x, y);
        if (!el || el.closest('#drawer')) continue;
        if (el.closest('.bar[data-run]') || el.closest('[data-go]') || el.closest('.cal-dot')) continue;
        if (isBoard && !el.closest('.board')) continue;
        return {x, y};
      }
    }
    return null;
  };
  const empty = emptySpot();
  if (empty) {
    const {x, y} = empty;
    await check('빈 영역 클릭', () => {
      const el = document.elementFromPoint(x, y);
      ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t =>
        el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, detail:1,
                                            clientX:x, clientY:y, view:window})));
    }, {mayClose: true});
    const closed = !dw.classList.contains('open');
    results.push((closed ? '✓' : '✗') + ' 빈 영역 클릭으로는 닫힌다');
    if (!closed) errors.push('빈 영역 클릭으로 닫히지 않음');
  } else results.push('· 화면 안에 빈 칸이 없어 건너뜀');

  /* ── 드래그로 닫히지 않는가 ────────────────────────────────────────
     브라우저는 누른 곳과 뗀 곳이 달라도 **둘의 공통 조상**에 click 을 낸다.
     그래서 click 하나만 보고 판정하면 드로어 안에서 눌러 보드 여백에서 뗀
     드래그가 「바깥 클릭」 이 된다 — 폭을 조절하다가도, 글자를 끌어
     선택하다가도 패널이 닫힌다.

     전에는 그 입구를 하나씩 막았다(폭 조절 핸들에 400ms 창). 핸들을 막았더니
     본문이 왔다. **그때 이 자리에 시험이 없어서 두 번째가 될 때까지 몰랐다.**

     아래는 실제로 이벤트를 쏜다 — 누르기는 안쪽 요소에, 떼기는 여백에,
     click 은 공통 조상(body)에. 진짜 드래그가 브라우저에서 그렇게 생겼다. */
  /* **움직임도 쏜다.** 옛 폭 조절 고침은 `moved`(2px 넘게 움직였나)가 참일
     때만 시각을 찍었다 — 움직임을 안 쏘면 되돌려 확인했을 때 무엇 때문에
     빨개졌는지 갈린다(down/up 인가, `moved` 가 거짓이어서인가).

     `공통` 이 `document.body` 인 것은 **누른 곳과 뗀 곳이 갈릴 때**의 모양이다 —
     브라우저는 둘의 가장 가까운 공통 조상에 click 을 낸다. 둘 다 드로어 안이면
     click 도 드로어 안에서 나므로, 그 경우는 아래에서 따로 넘긴다. */
  const 끌어보기 = async (label, 시작, x, y, opts = {}) => {
    const 뗄곳 = document.elementFromPoint(x, y) || document.body;
    const 공통 = opts.공통 || document.body;
    const 쏘기 = (el, t, ex, ey) => el.dispatchEvent(new PointerEvent(t,
      {bubbles: true, cancelable: true, clientX: ex ?? x, clientY: ey ?? y, view: window}));
    /* **`detail` 을 실어야 브라우저와 같다.** 포인터가 낸 클릭은 detail >= 1
       이고 키보드로 낸 것과 `.click()` 은 0 이다. 안 실으면 0 이 되어
       **진짜 드래그가 키보드 클릭 흉내가 된다** — 판정 쪽이 그 둘을
       가르므로, 안 실으면 재는 것이 실제와 달라진다. */
    const 마우스 = (el, t, ex, ey) => el.dispatchEvent(new MouseEvent(t,
      {bubbles: true, cancelable: true, detail: 1,
       clientX: ex ?? x, clientY: ey ?? y, view: window}));
    const r = 시작.getBoundingClientRect();
    const sx = Math.round(r.left + r.width / 2), sy = Math.round(r.top + r.height / 2);
    await check(label, async () => {
      쏘기(시작, "pointerdown", sx, sy);
      마우스(시작, "mousedown", sx, sy);
      // **느리게도 끌어 본다.** 한때 판정이 pointerdown 부터 시간을 재서,
      // 그보다 오래 끌면 고장이 그대로 났다 — 이벤트를 한 틱에 몰아 쏘면
      // 경과가 0ms 라 **언제나 초록이다.**
      if (opts.뜸) await sleep(opts.뜸);
      // 2px 을 확실히 넘겨 움직인다 — 옛 `moved` 가 참이 되는 자리다
      [12, 40, 0].forEach((d, i) => {
        const mx = i === 2 ? x : sx - d, my = i === 2 ? y : sy;
        쏘기(뗄곳, "pointermove", mx, my);
        마우스(뗄곳, "mousemove", mx, my);
      });
      쏘기(뗄곳, "pointerup");
      마우스(뗄곳, "mouseup");
      공통.dispatchEvent(new MouseEvent("click",
        {bubbles: true, cancelable: true, detail: 1,
         clientX: x, clientY: y, view: window}));
    }, opts);
  };

  if (empty) {
    const {x, y} = empty;

    // ③ **재는 것이 있는지 먼저 본다.** 드로어가 닫힌 채로 아래를 돌리면
    //    「닫히지 않았다」 가 언제나 참이라 시험이 통째로 헛돈다.
    openers()[0].click();
    await sleep(700);
    if (!dw.classList.contains("open")) {
      errors.push("드래그 시험 전에 드로어를 열지 못함 — 아래 셋은 아무것도 재지 못한다");
      results.push("✗ 드래그 시험을 위한 드로어 열기");
    } else {
      results.push("✓ 드래그 시험을 위한 드로어 열기");

      /* **각 항목은 앞 항목에 기대지 않는다.** 앞이 실패해 드로어가 닫히면
         뒤엣것은 `if (열려 있으면)` 에 걸려 **말없이 안 돌고**, 그러면
         "무엇이 고장인지" 가 아니라 "무엇을 쟀는지" 가 사라진다.
         고치기 전 코드로 되돌려 봤을 때 실제로 그랬다 — 본문 항목이
         빨개지자 핸들 항목이 아예 목록에 없었다. */
      const 열어둔다 = async 라벨 => {
        if (dw.classList.contains("open")) return true;
        openers()[0].click();
        await sleep(700);
        const ok = dw.classList.contains("open");
        if (!ok) results.push("· " + 라벨 + " — 드로어를 다시 못 열어 건너뜀");
        return ok;
      };

      // ② 안에서 눌러 여백에서 뗌 — 글자를 끌어 선택하는 그 동작이다
      const 본문 = () => dw.querySelector(".dbody, .pane.on, #dlog") || dw;
      if (await 열어둔다("본문 드래그"))
        await 끌어보기("드로어 본문에서 눌러 여백에서 뗌", 본문(), x, y);

      // ② **느린 드래그.** 글자를 끌어 선택하는 것은 1.5초를 흔히 넘는다.
      if (await 열어둔다("느린 본문 드래그"))
        await 끌어보기("드로어 본문에서 2초 끌다 여백에서 뗌", 본문(), x, y,
                     {뜸: 2000, wait: 700});

      /* ② 폭 조절 핸들에서 눌러 여백에서 뗌 — **지난번에 고친 그것이다.**
         그때 400ms 창으로 막았고 시험은 없었다.

         **이 항목은 고치기 전 코드에서도 통과한다** — 400ms 창이 실제로
         막고 있었기 때문이다(움직임을 쏘아 `moved` 를 참으로 만들면 그렇다).
         그러니 이 항목이 잡는 것은 이번 버그가 아니라 **회귀**다: 400ms 창을
         걷어낸 자리를 down/up 이 정말로 대신하는가. 이번 버그를 잡는 것은
         바로 위의 본문 항목이다. */
      if (await 열어둔다("핸들 드래그")) {
        const 원래폭 = getComputedStyle(document.documentElement).getPropertyValue("--dw");
        await 끌어보기("폭 조절 핸들에서 눌러 여백에서 뗌", $("grip"), x, y);
        // **폭을 되돌린다.** 움직임을 쏘면 핸들이 진짜로 폭을 바꾸고,
        // 그러면 처음에 찾아 둔 여백 좌표가 더 이상 여백이 아니다 —
        // 뒤 항목이 "고침이 과하다" 로 잘못 빨개진다. 실제로 한 번 그랬다.
        document.documentElement.style.setProperty("--dw", 원래폭.trim() || "440px");
        await sleep(250);
      }

      // ② 안에서 눌러 안에서 뗌.
      //    **브라우저에서는 원래 고장나지 않던 모양이다** — 둘 다 안이면 click 도
      //    드로어 안에서 나므로 옛 코드도 이건 막았다. 그래서 click 을 body 가
      //    아니라 드로어에 내야 실제와 같다. 새 down/up 논리의 회귀 방어로 둔다.
      if (await 열어둔다("안→안 드래그")) {
        const r = dw.getBoundingClientRect();
        const ix = Math.round(r.left + r.width / 2), iy = Math.round(r.top + r.height / 2);
        await 끌어보기("안에서 눌러 안에서 뗌 (원래 안 닫히던 모양 · 회귀 방어)",
                     본문(), ix, iy, {공통: dw});
      }

      // ① 반대편 — 여백을 **그냥 눌렀다 떼면** 닫혀야 한다.
      //    과하게 걸려 정작 닫혀야 할 때 안 닫히면 그것도 고장이다.
      if (await 열어둔다("여백 클릭")) {
        // **여백을 다시 찾는다** — 위 드래그들이 폭을 건드렸을 수 있다
        const 다시 = emptySpot() || {x, y};
        const el = document.elementFromPoint(다시.x, 다시.y);
        await check("여백을 눌렀다 뗌", () => {
          ["pointerdown","mousedown","pointerup","mouseup","click"].forEach(t =>
            el.dispatchEvent(new MouseEvent(t,
              {bubbles: true, cancelable: true, detail: 1,
               clientX: 다시.x, clientY: 다시.y, view: window})));
        }, {mayClose: true});
        const 닫힘 = !dw.classList.contains("open");
        results.push((닫힘 ? "✓" : "✗") + " 여백을 눌렀다 떼면 닫힌다 (드래그 고침이 과하지 않다)");
        if (!닫힘) errors.push("드래그 고침이 과해서 여백 클릭으로도 안 닫힘");
      }

      /* **click 없이 끝난 포인터 뒤의 키보드 클릭.**
         오른쪽 버튼은 click 을 내지 않아서 기록이 남는다. 그 뒤 pointerdown 이
         없는 클릭(포커스 + 엔터)이 오면 옛 값을 써서 **닫혀야 할 때 안 닫힌다.**
         고치는 쪽이 과했을 때 나는 고장이라 반대편으로 잰다. */
      if (await 열어둔다("우클릭 뒤 키보드 클릭")) {
        const 본문2 = dw.querySelector(".pane.on") || dw;
        본문2.dispatchEvent(new PointerEvent("pointerdown",
          {bubbles: true, cancelable: true, button: 2, view: window}));
        본문2.dispatchEvent(new MouseEvent("contextmenu", {bubbles: true, cancelable: true, view: window}));
        await sleep(120);
        // 키보드 클릭 — pointerdown 이 없다
        const 저기 = emptySpot() || {x, y};
        const 밖 = document.elementFromPoint(저기.x, 저기.y);
        밖.dispatchEvent(new MouseEvent("click",
          {bubbles: true, cancelable: true, clientX: 저기.x, clientY: 저기.y, detail: 0, view: window}));
        await sleep(600);
        const 닫힘2 = !dw.classList.contains("open");
        results.push((닫힘2 ? "✓" : "✗") + " 우클릭 뒤 키보드 클릭으로도 닫힌다 (옛 기록이 안 남는다)");
        if (!닫힘2) errors.push("우클릭 뒤 키보드 클릭에서 옛 down/up 기록이 남아 안 닫힘");
      }
    }
  } else {
    // **왜 줄었는지 화면에 남긴다** (11-3). 없으면 항목 수만 일곱 줄고
    // 사람은 스크립트가 망가진 줄 안다.
    results.push("· 화면 안에 빈 칸이 없어 드래그 시험 여섯 · 결과 줄 여덟을 건너뜀");
  }

  // 닫은 뒤에도 보던 자리가 그대로인가 — 달력은 특히 보던 달을 잃으면 안 된다
  if (calbar) {
    const kept = calbar.dataset.month && location.pathname.startsWith('/calendar');
    results.push((kept ? '✓' : '✗') + ` 닫아도 보던 달이 그대로 (${calbar.dataset.month})`);
    if (!kept) errors.push('닫았더니 보던 달을 잃음');
  }

  // 달력 탭은 드로어를 넓혀도 커지지 않아야 한다 — 한 화면에 들어와야 하므로
  openers()[0].click();
  await sleep(700);
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

  // ── 화면마다 다른 두 가지 ─────────────────────────────────────────
  //    패널은 한 벌이지만 그것을 담은 화면은 각자의 규칙이 있다.
  if (isBoard) {
    // 가로 격자선을 넣지 않는다 (CLAUDE.md 4-0).
    // 세로선은 남기므로 '선이 하나도 없다'가 아니라 '가로선만 없다'를 본다.
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

    // 왼쪽 목록은 sticky 로 떠 있어 그 아래로 바가 지나간다. 배경이 반투명하면
    // **뒤의 바가 비친다.** CSS 에 규칙이 있다는 것만으로는 뒤엣것이 이기는지
    // 알 수 없으므로 **계산된 스타일**로 본다 (10장).
    const 불투명 = el => {
      const bg = getComputedStyle(el).backgroundColor;
      const m = bg.match(/^rgba?\(([^)]+)\)/);
      if (!m) return false;
      const parts = m[1].split(',').map(v => parseFloat(v));
      return parts.length < 4 || parts[3] >= 1;   // 알파가 없거나 1 이면 불투명
    };
    // `:hover` 는 스크립트로 켤 수 없다. 그래서 CSS 의 호버 규칙에 `.is-hover`
    // 를 함께 달아 두고(retreat.css), **실제 요소에 그 클래스를 붙여** 실제
    // 트리에서 계산된 배경을 읽는다. 선언만 떠서 탐침에 얹으면 캐스케이드가
    // 없어서, 뒤엣것이 앞엣것을 이기는 그 버그가 다시 나도 초록이 된다.
    const 잰다 = async (el, cls) => {
      el.classList.add(cls);
      await sleep(40);
      const ok = 불투명(el);
      el.classList.remove(cls);
      await sleep(20);
      return ok;
    };
    const main = [...sheet.querySelectorAll('.row.main .lc, .row.sub .lc')].filter(shown)[0];
    const team = [...sheet.querySelectorAll('.row.team .lc')].filter(shown)[0];
    if (main && team) {
      const 잰값 = {
        평소: 불투명(main),
        호버: await 잰다(main, 'is-hover'),
        부서호버: await 잰다(team, 'is-hover'),
        연결: await 잰다(main.closest('.row'), 'hl') && true,
      };
      // `.hl`·`.anchorrow` 는 줄에 붙으므로 줄에 붙였다 뗀 뒤 칸을 다시 잰다
      const row = main.closest('.row');
      row.classList.add('hl'); await sleep(40);
      잰값.연결 = 불투명(main);
      row.classList.remove('hl');
      row.classList.add('anchorrow'); await sleep(40);
      잰값.선택 = 불투명(main);
      row.classList.remove('anchorrow'); await sleep(20);

      const ok = Object.values(잰값).every(Boolean);
      results.push((ok ? '✓' : '✗') + ' 왼쪽 라벨 열이 불투명 ('
        + Object.entries(잰값).map(([k, v]) => `${k} ${v ? 'O' : 'X'}`).join(' · ') + ')');
      if (!ok) errors.push('왼쪽 라벨 열 배경이 반투명 — 뒤의 바가 비친다');
    }
  } else {
    // 달력은 **마감일에 점 하나**다. 기간 띠가 아니다 (CLAUDE.md 4-13).
    const dots = document.querySelectorAll('.cal-dot').length;
    results.push((dots > 0 ? '✓' : '✗') + ` 마감일에 점이 그려짐 (${dots}개)`);
    if (!dots) errors.push('달력에 점이 없음');
    // 날짜 없는 업무를 조용히 빼지 않는다 — 있을 때만 본다
    const undated = document.querySelector('.calundated');
    results.push('✓ 날짜 없는 업무 자리 ' + (undated ? '있음(펼치면 목록)' : '이번 달엔 해당 없음'));

    // 점에 마우스를 올리면 그 업무의 기간이 비친다 (4-13).
    // **마감일에 점 하나** 는 그대로다 — 한 번에 하나만, 떼면 사라진다.
    const withSpan = [...document.querySelectorAll('.cal-dot[data-start]')].filter(shown);
    if (withSpan.length && matchMedia('(min-width: 821px)').matches) {
      const dot = withSpan.find(d => d.dataset.start !== d.dataset.end) || withSpan[0];
      dot.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
      await sleep(80);
      const 칠해진 = [...document.querySelectorAll('.cal-cell.inspan')];
      const 맞는가 = 칠해진.length > 0 && 칠해진.every(td =>
        dot.dataset.start <= td.dataset.date && td.dataset.date <= dot.dataset.end);
      results.push((맞는가 ? '✓' : '✗')
        + ` 점에 올리면 기간이 비침 (${칠해진.length}칸)`);
      if (!맞는가) errors.push('기간 비침이 동작하지 않음');

      // 오늘 칸의 파란 테두리가 비침에 덮이지 않는다
      const today = document.querySelector('.cal-cell.today');
      if (today) {
        const 남음 = getComputedStyle(today).boxShadow !== 'none';
        results.push((남음 ? '✓' : '✗') + ' 오늘 칸 테두리가 비침 위에 남음');
        if (!남음) errors.push('오늘 칸 테두리가 덮임');
      }

      dot.dispatchEvent(new MouseEvent('mouseout', {bubbles: true, relatedTarget: document.body}));
      await sleep(80);
      const 지워짐 = document.querySelectorAll('.cal-cell.inspan').length === 0;
      results.push((지워짐 ? '✓' : '✗') + ' 손을 떼면 사라짐');
      if (!지워짐) errors.push('비침이 남아 있음');
    } else results.push('· 기간을 가진 점이 없거나 좁은 화면이라 건너뜀');
  }

  console.table(results);
  return {화면: where, 통과: errors.length === 0, 실패: errors,
          항목수: results.length, 항목: results};
})()
