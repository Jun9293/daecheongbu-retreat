/* 재정 화면(예산 · 지출) 상호작용 점검 — **표를 고치는 것이 실제로 되는가.**
 *
 * 쓰는 법: **예산(/budget) 또는 지출(/expenses)** 을 연 뒤 브라우저 콘솔에
 * 이 파일 내용을 붙여넣습니다. 두 화면에서 각각 돌립니다.
 *
 * **왜 따로 만들었나 — `docs/checks/drawer.js` 를 안 넓혔습니다.**
 * 그쪽은 **상세 패널이 있는 화면**(보드 · 달력 · 목록)을 전제하고 맨 앞에서
 * `#drawer` 를 찾습니다. 재정 화면에는 그 패널이 아예 없어서, 한 파일에
 * 넣으면 그쪽 항목이 통째로 「건너뜀」 으로 빠져 **「N/N 통과」 가 뜻을
 * 잃습니다** — `phone.js` 를 따로 둔 것과 같은 자리입니다. 재는 전제가
 * 다르면 파일도 다릅니다.
 *
 * **왜 생겼나** — 2026-09-26 에 예산 · 지출 화면을 시트 모양으로 다시
 * 만들면서 **끌어 옮기기**와 **팝업 셋**(긴 내용 · 계좌 · 영수증)이
 * 들어왔는데, 둘 다 **pytest 가 못 보는 자리**입니다(10장) —
 * `dragstart`/`drop` 도 호버 유지도 브라우저에서만 돕니다. 실제로 그 판은
 * 화면 점검을 못 돌린 채 끝났고 봐둘것 BJ-i 가 그것을 이어받았습니다.
 *
 * 무엇을 보는가 —
 *   · 「전체 편집」 을 누르면 표가 편집 상태가 되는가
 *   · **편집이 꺼져 있으면 이동 핸들이 안 보이는가** (막는 쪽)
 *   · 이동 핸들이 **실제로 끌리는가** — 끌어다 놓으면 줄 차례가 바뀌는가
 *   · 구분마다 소계 줄이 서고 제목이 예산금액 바로 왼쪽인가
 *   · 줄을 더하고 뺄 수 있는가 (빼는 것은 취소 표시다 — 0장)
 *   · 팝업 셋이 뜨고 · **화면 밖으로 안 나가고** · 바깥을 누르면 닫히는가
 *   · 계좌 팝업은 마우스를 옮기면 유지되고 벗어나면 닫히는가
 *   · **영수증이 없는 줄에는 「영수증 추가」 가 안 뜨는가** (막는 쪽)
 *   · **편집 중에는 팝업이 안 열리는가** (저장 안 한 칸이 사라지지 않게)
 *
 * **저장을 누르지 않습니다.** 이 점검이 재는 것은 「화면이 도는가」 이고,
 * 저장은 되돌릴 수 없는 자국을 남깁니다 — 활동 기록에 줄이 남고 취소는
 * 행을 아래로 내립니다(10장 · 봐둘것 BI-j 의 그 규칙). 그래서 마지막에
 * 늘 **「되돌리기」 로 편집을 끕니다**: 표는 서버에서 다시 그려집니다.
 *
 * **자가시험** — 붙여넣기 전에 `window.__자가시험 = 1;` 을 실행하면 갈래마다
 * 고장을 하나씩 심었다 걷어내며 그 갈래가 기다리는 답이 나오는지 잽니다.
 * 점검 스크립트를 고친 판에서는 반드시 돌립니다 (11-3 2단계).
 */
(async () => {
const sleep = ms => new Promise(r => setTimeout(r, ms));

const 점검 = async () => {
  const $ = id => document.getElementById(id);
  const errors = [], results = [], 못쟀음 = [];

  /* ✗ 를 찍는 길과 세는 길은 하나다 — 둘이면 손으로 맞추게 되고 실제로
     어긋난 적이 있다(`drawer.js` 의 그 자리). */
  const 잰다 = (ok, 라벨, 까닭) => {
    results.push((ok ? '✓' : '✗') + 라벨);
    if (!ok) errors.push(까닭 === undefined ? 라벨.trim() : 까닭);
    return ok;
  };
  /* **기다리지 말고 본다** — 시간을 어림으로 박으면 검사가 흔들린다.
     상한에 걸린 것은 ✗ 가 아니라 **「못 쟀음」** 이다(`drawer.js` 의 그 규칙). */
  const 될때까지 = async (무엇, 조건, 상한 = 2000) => {
    const 끝 = Date.now() + 상한;
    for (;;) {
      let ok = false;
      try { ok = !!조건(); } catch (e) { ok = false; }
      if (ok) return true;
      if (Date.now() >= 끝) { 못쟀음.push(무엇); return false; }
      await sleep(25);
    }
  };
  /* **안 되는 것이 답인 자리**는 「못 쟀음」 이 아니다 — 「닫혀야 하는데
     안 닫힌다」 는 화면의 고장이라 ✗ 로 세야 한다. */
  const 잠깐본다 = async (조건, 상한 = 1200) => {
    const 끝 = Date.now() + 상한;
    for (;;) {
      let ok = false;
      try { ok = !!조건(); } catch (e) { ok = false; }
      if (ok || Date.now() >= 끝) return ok;
      await sleep(25);
    }
  };

  const 예산표 = $('budtbl');
  const 지출표 = document.querySelector('table.exptbl');
  if (!예산표 && !지출표) return {치명: '이 화면에는 재정 표가 없습니다'
    + ' — 예산(/budget) 이나 지출(/expenses) 에서 돌리세요.'};
  const 예산인가 = !!예산표;
  const 표 = 예산표 || 지출표;
  const where = 예산인가 ? '예산' : '지출';

  /* **편집을 켜는 단추가 없으면 그 계정은 못 고치는 쪽이다** — 예산은
     총무팀만 고치므로(7-3) 부서 리더에게는 이 단추가 아예 없다. 그때
     「이 계정에는 없다」 로 세는 것이 맞다: ✗ 로 세면 권한대로 그려진
     화면이 빨개진다. */
  const 편집단추 = $(예산인가 ? 'budedit' : 'expedit');
  const 띠 = $(예산인가 ? 'budbar' : 'expbar');
  const 되돌림 = $(예산인가 ? 'budcancel' : 'expcancel');
  const 고칠수있나 = !!(편집단추 && 편집단추.offsetParent);

  const shown = el => !!(el && el.offsetParent);
  const 화면안 = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0
      && r.left >= -1 && r.top >= -1
      && r.right <= window.innerWidth + 1 && r.bottom <= window.innerHeight + 1;
  };
  const 편집중 = () => 표.classList.contains('editing');
  /* **보는 판과 편집 판의 줄 표시가 다르다** — 서버가 그린 줄은 `data-cat`
     이고 `budget.js` 가 다시 그린 줄은 `data-i` 다(7-3 — 편집은 한 모델에서
     다시 그린다). 한쪽만 찾으면 **줄이 있는데 0줄로 세어** 첫 항목부터
     빨개진다(2026-09-26 에 실제로 그랬다). */
  const 줄들 = () => [...표.querySelectorAll(예산인가
    ? 'tbody tr[data-cat], tbody tr[data-i]' : 'tbody tr[data-exp]')];

  /* ── 전제: 이 화면의 폭 ──────────────────────────────────────────
     **좁은 화면에서도 돈다** — 재정 표는 가로로 넘겨 보는 표라 폭이
     갈래를 바꾸지 않는다. 다만 호버로 뜨는 것(계좌 팝업)은 손가락
     기기에 없으므로 그 자리는 **누름으로** 연다(아래). */
  const 폭 = window.innerWidth;
  const 호버있나 = matchMedia('(hover: hover)').matches;

  // ── ① 표가 그려졌는가 ───────────────────────────────────────────
  잰다(줄들().length > 0, ` ${where} 표에 줄이 있다 (${줄들().length}줄)`,
       `${where} 표가 비어 있다 — 자료가 있는 회차에서 돌리세요`);

  // ── ② 편집이 꺼져 있으면 고치는 자리가 안 보인다 (막는 쪽) ──────
  /* 예산은 이동 핸들, 지출은 줄 끝의 편집 칸이 그 자리다. 둘 다
     **편집 상태에서만** 있어야 한다 (7-3 · 7-4). */
  const 꺼진핸들 = [...표.querySelectorAll('.grip')].filter(shown);
  const 꺼진편집칸 = [...표.querySelectorAll('td.editcell')].filter(shown);
  잰다(꺼진핸들.length === 0 && 꺼진편집칸.length === 0,
       ' 편집이 꺼져 있으면 고치는 자리가 안 보인다',
       `편집이 꺼졌는데 핸들 ${꺼진핸들.length}개 · 편집 칸 ${꺼진편집칸.length}개가 보인다`);

  // ── ③ 소계 · 병합 ───────────────────────────────────────────────
  if (예산인가) {
    const 소계 = [...표.querySelectorAll('tr.subtot')];
    const 구분 = [...표.querySelectorAll('td.l1')].filter(td => !td.closest('tr.canceled'));
    잰다(소계.length > 0 && 소계.length === 구분.length,
         ` 구분마다 소계 줄이 있다 (구분 ${구분.length} · 소계 ${소계.length})`,
         `구분 ${구분.length}개인데 소계가 ${소계.length}개다`);
    const 제목칸 = 소계.length ? 소계[0].querySelector('td.r') : null;
    잰다(!!(제목칸 && 제목칸.colSpan === 6),
         ' 「소계」 제목이 예산금액 바로 왼쪽이다',
         '소계 제목의 colspan 이 6 이 아니다 — 예산금액 칸과 어긋난다');
    /* 병합이 실제로 서는가 — 구분 칸은 그 구분의 세부항목 줄만큼 걸친다.
       **rowspan 이 1 뿐이면 병합이 죽은 것**이고, 그때 화면은 구분이
       줄마다 서는 옛 모양으로 돌아간다. */
    const 걸친것 = 구분.filter(td => td.rowSpan > 1);
    if (구분.length > 1 || (구분[0] && 구분[0].rowSpan > 1)) {
      잰다(걸친것.length > 0, ` 구분 칸이 세로로 병합된다 (${걸친것.length}개)`,
           '구분 칸이 하나도 안 병합됐다');
    } else results.push('· 구분마다 세부항목이 하나뿐이라 병합은 건너뜀');
  } else {
    const 예산항목칸 = [...표.querySelectorAll('td.catcell')];
    잰다(예산항목칸.length > 0, ` 예산 항목이 묶음마다 한 칸이다 (${예산항목칸.length}묶음)`,
         '지출 표에 예산 항목 칸이 없다');
    /* **칸 격자를 세어 본다** — 병합 수가 그려질 줄 수와 어긋나면 그 묶음
       아래가 통째로 밀린다(7-4 · 커밋 전 검토 [C]).

       **자리로는 못 잰다.** 처음에는 「오른쪽 끝이 같은가」 로 쟀는데,
       `table-layout:fixed` 가 열 너비를 `<colgroup>` 에서 받으므로 **어긋나도
       끝은 같은 자리**다 — 자가시험이 그것을 「놓침」 으로 잡아 알았다.
       그래서 **rowspan · colspan 을 따라가며 칸을 세고**(머리글 · 긴 내용
       줄까지 전부) 줄마다 같은 수인지 본다. */
    const 격자 = () => {
      const 찬칸 = {};
      return [...표.querySelectorAll('tbody tr')].map(tr => {
        let 열 = 0;
        [...tr.children].forEach(td => {
          while (찬칸[열] > 0) 열++;
          const 폭 = td.colSpan || 1, 높 = td.rowSpan || 1;
          for (let i = 0; i < 폭; i++) 찬칸[열 + i] = 높;
          열 += 폭;
        });
        while (찬칸[열] > 0) 열++;
        Object.keys(찬칸).forEach(k => 찬칸[k]--);
        return 열;
      });
    };
    const 끝열 = 격자();
    const 머리칸 = 표.querySelectorAll('thead th').length;
    잰다(끝열.length > 0 && 끝열.every(x => x === 머리칸),
         ` 줄마다 칸이 머리글과 같다 (머리 ${머리칸} · 줄 ${[...new Set(끝열)].join('/')})`,
         `줄마다 칸이 밀려 있다 — 머리 ${머리칸}칸인데 줄은 ${[...new Set(끝열)].join('/')}칸이다`);
  }

  // ── ④ 전체 편집을 켠다 ──────────────────────────────────────────
  let 켰다 = false;
  if (!고칠수있나) {
    results.push('· 이 계정에는 「전체 편집」 이 없어 편집 갈래를 건너뜀');
  } else {
    편집단추.click();
    const 켜짐 = await 될때까지('편집 상태', () => 편집중() && shown(띠));
    켰다 = 켜짐;
    잰다(켜짐, ' 「전체 편집」 을 누르면 표가 편집 상태가 된다',
         '「전체 편집」 을 눌러도 편집 상태가 안 된다');
  }

  if (켰다) {
    // ── ⑤ 편집 상태에서만 고치는 자리가 뜬다 ────────────────────
    if (예산인가) {
      const 핸들 = [...표.querySelectorAll('.grip')].filter(shown);
      const 항목핸들 = 핸들.filter(g => g.dataset.grip === 'item');
      const 줄핸들 = 핸들.filter(g => g.dataset.grip === 'row');
      잰다(항목핸들.length > 0 && 줄핸들.length > 0,
           ` 이동 핸들이 둘 다 뜬다 (항목 ${항목핸들.length} · 세부항목 ${줄핸들.length})`,
           '편집을 켰는데 이동 핸들이 없다');

      // ── ⑥ 줄을 먼저 더한다 — 그래야 끌 줄이 둘이 된다 ──────────────────────────────────────────
      const 줄추가 = $('budadd');
      if (!shown(줄추가)) results.push('· 「+ 줄 추가」 가 없어 건너뜀');
      else {
        const 전수 = 줄들().length;
        줄추가.click();
        await 될때까지('줄 추가', () => 줄들().length === 전수 + 1);
        잰다(줄들().length === 전수 + 1, ` 「+ 줄 추가」 로 줄이 하나 는다 (${전수} → ${줄들().length})`,
             '「+ 줄 추가」 를 눌러도 줄이 안 는다');
      }

      // ── ⑦ 끌어 옮기기가 실제로 먹는가 ──────────────────────────
      /* **여기가 pytest 가 못 보는 자리다** — 모델 쪽은 `test73` 이 잡지만
         `dragstart`/`drop` 은 브라우저에서만 돈다. 세부항목 하나를 다른
         줄 위로 끌어다 놓고 **차례가 실제로 바뀌는지** 본다.

         **줄 추가를 먼저 한 것은 그 때문이다** — 자료가 얇은 회차에서는
         줄이 하나뿐이라 이 항목이 통째로 건너뛰어지는데, 그러면 **가장
         못 보던 자리를 또 안 보게** 된다. 더한 줄은 저장하지 않으므로
         「되돌리기」 로 함께 사라진다. */
      const 줄 = 줄들();
      if (줄.length < 2 || !줄핸들.length) {
        results.push('· 끌어 옮길 줄이 둘이 안 되어 건너뜀');
      } else {
        const 이름 = tr => (tr.querySelector('[data-f="level3"]') || {}).value
          || (tr.querySelector('td.l3') || {}).textContent || '';
        const 전 = 줄들().map(이름);
        const 잡을것 = 줄들().find(tr => tr.querySelector('.grip[data-grip="row"]'));
        const 놓을것 = 줄들().reverse().find(tr => tr !== 잡을것);
        const dt = new DataTransfer();
        /* **놓는 자리의 위아래가 뜻을 바꾼다** — 화면은 `clientY` 가 그 줄의
           절반보다 아래면 「뒤에」, 위면 「앞에」 로 읽는다. 좌표를 안 주면
           0 이 되어 늘 「앞에」 가 되고, **바로 다음 줄 앞에 놓는 것은 제자리**라
           차례가 안 바뀐다 — 끌기가 멀쩡해도 ✗ 가 난다(2026-09-26 에 실제로
           그렇게 나왔고, 그때 틀린 것은 화면이 아니라 이 검사였다). */
        const r = 놓을것.getBoundingClientRect();
        const 쏜다 = (el, 무엇) => el.dispatchEvent(new DragEvent(무엇, {
          bubbles: true, cancelable: true, dataTransfer: dt,
          clientX: Math.round(r.left + 8), clientY: Math.round(r.bottom - 2)}));
        쏜다(잡을것.querySelector('.grip[data-grip="row"]'), 'dragstart');
        쏜다(놓을것, 'dragover');
        쏜다(놓을것, 'drop');
        await 될때까지('끌어 옮긴 뒤의 표', () => 줄들().map(이름).join('|') !== 전.join('|'));
        const 후 = 줄들().map(이름);
        잰다(후.join('|') !== 전.join('|'),
             ' 세부항목을 끌어다 놓으면 차례가 바뀐다',
             '끌어다 놓아도 줄 차례가 그대로다 — 끌기가 안 먹는다');
        잰다(후.length === 전.length && 후.slice().sort().join('|') === 전.slice().sort().join('|'),
             ' 끌어도 줄이 늘거나 줄지 않는다',
             `끌었더니 줄 수가 ${전.length} → ${후.length} 로 바뀌었다`);
      }

      // ── ⑧ 금액은 편집 중에도 천 단위 콤마 ──────────────────────
      const 금액칸 = [...표.querySelectorAll('input.bi[data-f="planned_amount"]')].filter(shown)[0];
      if (!금액칸) results.push('· 예산금액 입력칸이 없어 콤마는 건너뜀');
      else {
        금액칸.focus();
        금액칸.value = '1234567';
        금액칸.dispatchEvent(new Event('input', {bubbles: true}));
        await 잠깐본다(() => 금액칸.value.includes(','));
        잰다(금액칸.value.includes(','), ` 편집 중에도 천 단위 콤마 (${금액칸.value})`,
             '편집 중에 금액에 콤마가 안 붙는다');
      }
    } else {
      // 지출 — 편집 상태에서 줄 끝에 칸이 하나 는다 (예산 항목 · 취소)
      const 편집칸 = [...표.querySelectorAll('td.editcell')].filter(shown);
      잰다(편집칸.length > 0, ` 편집 상태에서 줄 끝에 칸이 는다 (${편집칸.length}줄)`,
           '편집을 켰는데 줄 끝 칸이 안 생긴다');
      /* **못 고치는 줄에도 칸을 더한다** — 안 그러면 그 줄만 칸 수가
         모자라 표가 통째로 밀린다(BJ-i 가 적어 둔 자리). */
      const 칸수 = 줄들().map(tr => tr.children.length);
      잰다(new Set(칸수).size <= 2, ` 편집 중에도 줄마다 칸 수가 고르다 (${[...new Set(칸수)].join('/')})`,
           `편집을 켜니 줄마다 칸 수가 ${[...new Set(칸수)].join('/')} 로 갈린다`);

      // ── 편집 중에는 팝업이 안 열린다 (검토 [I]) ─────────────────
      /* **긴 내용 칸은 그 지출 줄 안에 없다** — 아래에 따로 서는 줄
         (`tr.longrow[data-of]`)에 있다. `closest('tr[data-exp]')` 로 찾으면
         늘 `null` 이라 이 갈래가 통째로 건너뛰어진다(2026-09-26 에 실제로
         그랬다 — 검토 [I] 가 막은 자리를 아무도 안 재고 있었다). */
      const 줄찾기 = b => {
        const 긴줄 = b.closest('tr.longrow');
        const id = 긴줄 ? 긴줄.dataset.of : null;
        return id ? 표.querySelector(`tr[data-exp="${id}"]`) : b.closest('tr[data-exp]');
      };
      const 긴칸 = [...표.querySelectorAll('.longcell')].filter(shown)
        .find(b => (줄찾기(b) || {dataset: {}}).dataset.edit === '1');
      if (!긴칸) results.push('· 편집 중 팝업 막기 — 고칠 수 있는 긴 내용 줄이 없어 건너뜀');
      else {
        긴칸.click();
        await 잠깐본다(() => !!document.querySelector('.exppop'));
        const 팝 = document.querySelector('.exppop');
        const 막았나 = !!팝 && /편집을 저장하거나/.test(팝.textContent);
        잰다(막았나, ' 편집 중에는 팝업 대신 까닭을 말한다',
             '편집 중에 팝업이 그대로 열린다 — 저장 안 한 칸이 사라진다');
        /* **갈래가 끝나면 연 것을 닫는다** — 남겨 두면 그 뒤의 줄이 같은
           자리를 눌렀을 때 옛 팝업을 그대로 받는다(11-3 의 그 규칙). */
        document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
        document.body.click();
        await 잠깐본다(() => !document.querySelector('.exppop'));
      }
    }

    // ── ⑨ 되돌리기 ──────────────────────────────────────────────
    /* **저장은 안 누른다**(머리말) — 되돌리면 표가 서버 판으로 돌아온다. */
    if (!shown(되돌림)) results.push('· 「되돌리기」 가 없어 건너뜀');
    else {
      되돌림.click();
      const 꺼짐 = await 될때까지('편집 끄기', () => !편집중() && !shown(띠));
      잰다(꺼짐, ' 「되돌리기」 로 편집이 꺼진다', '「되돌리기」 를 눌러도 편집이 안 꺼진다');
      const 남은핸들 = [...표.querySelectorAll('.grip')].filter(shown);
      잰다(남은핸들.length === 0, ' 편집을 끄면 핸들이 사라진다',
           `편집을 껐는데 핸들 ${남은핸들.length}개가 남았다`);
    }
  }

  // ── ⑩ 팝업 셋 (지출만) ─────────────────────────────────────────
  if (!예산인가) {
    /* **닫는 길은 `pointerdown` 이고 그 대상이 요소여야 한다** — 팝업은
       `e.target instanceof Element` 를 먼저 보므로 `document` 에 쏘면 아무
       일도 안 난다. 안 닫힌 채로 다음 줄이 가면 **같은 자리를 다시 눌러도
       팝업이 그대로**라(`띄운다` 가 같은 주인이면 되돌려 준다) 엉뚱한 줄이
       ✗ 가 된다 — 2026-09-26 에 실제로 그랬고 틀린 것은 검사였다. */
    const 팝닫기 = async () => {
      document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
      document.body.click();
      await 잠깐본다(() => !document.querySelector('.exppop'));
    };

    // 긴 내용 — 누르면 전체가 뜨고, 화면 밖으로 안 나가고, 바깥을 누르면 닫힌다
    const 긴칸 = [...표.querySelectorAll('.longcell')].filter(shown)[0];
    if (!긴칸) results.push('· 긴 내용(명단 · 비고)이 있는 줄이 없어 건너뜀');
    else {
      긴칸.click();
      const 떴나 = await 될때까지('긴 내용 팝업', () => !!document.querySelector('.exppop.longpop'));
      const 팝 = document.querySelector('.exppop.longpop');
      잰다(떴나 && !!팝, ' 긴 내용을 누르면 팝업이 뜬다', '긴 내용 팝업이 안 뜬다');
      if (팝) {
        잰다(화면안(팝), ' 긴 내용 팝업이 화면 안에 있다', '긴 내용 팝업이 화면 밖으로 나갔다');
        const 전체 = (긴칸.dataset.full || '').trim();
        잰다(!전체 || 팝.textContent.includes(전체.slice(0, 8)),
             ' 팝업이 줄이지 않은 전체를 보인다', '팝업에 전체 내용이 없다');
      }
      await 팝닫기();
      잰다(!document.querySelector('.exppop'), ' 바깥을 누르면 팝업이 닫힌다',
           '바깥을 눌러도 팝업이 안 닫힌다');
    }

    // 계좌 — 이름에 올리면 뜨고, 팝업으로 옮기면 유지되고, 벗어나면 닫힌다
    const 이름칸 = [...표.querySelectorAll('.payer.acct')].filter(shown)[0];
    if (!이름칸) {
      results.push('· 계좌가 적힌 지출이 없거나 이 계정은 계좌를 못 봐 건너뜀');
    } else {
      이름칸.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
      const 떴나 = await 될때까지('계좌 팝업', () => !!document.querySelector('.exppop.acctpop'));
      const 팝 = document.querySelector('.exppop.acctpop');
      잰다(떴나 && !!팝, ' 지출자 이름에 올리면 계좌 팝업이 뜬다', '계좌 팝업이 안 뜬다');
      if (팝) {
        잰다(화면안(팝), ' 계좌 팝업이 화면 안에 있다', '계좌 팝업이 화면 밖으로 나갔다');
        /* **보이는지까지 본다** — 숨은 단추는 없는 것과 같다(10장 「속성이
           아니라 화면을 확인한다」). 있는지만 보면 `display:none` 이 안 걸린다 */
        잰다(shown(팝.querySelector('.acctcopy')), ' 계좌 팝업에 「복사」 가 있다',
             '계좌 팝업에 복사 단추가 없거나 안 보인다');
        // 마우스를 팝업으로 옮기면 유지된다 — 이름에서 떼고 팝업으로 들어간다
        이름칸.dispatchEvent(new MouseEvent('mouseout', {bubbles: true, relatedTarget: 팝}));
        팝.dispatchEvent(new MouseEvent('mouseenter', {bubbles: false}));
        await sleep(320);
        잰다(!!document.querySelector('.exppop.acctpop'),
             ' 마우스를 팝업으로 옮기면 유지된다', '팝업으로 옮기는 사이에 닫힌다');
      }
      await 팝닫기();
      잰다(!document.querySelector('.exppop'), ' 계좌 팝업도 바깥을 누르면 닫힌다',
           '계좌 팝업이 안 닫힌다');
    }

    // 영수증 — 칩을 누르면 팝업, 고칠 수 있는 줄에만 추가·삭제
    const 칩 = [...표.querySelectorAll('.rcptchip')].filter(shown)[0];
    if (!칩) results.push('· 영수증이 걸린 지출이 없어 건너뜀');
    else {
      const 그줄 = 칩.closest('tr[data-exp]');
      const 고칠수있는줄 = 그줄 && 그줄.dataset.edit === '1';
      칩.click();
      const 떴나 = await 될때까지('영수증 팝업', () => !!document.querySelector('.exppop.rcptpop'));
      const 팝 = document.querySelector('.exppop.rcptpop');
      잰다(떴나 && !!팝, ' 영수증 칩을 누르면 팝업이 뜬다', '영수증 팝업이 안 뜬다');
      if (팝) {
        잰다(화면안(팝), ' 영수증 팝업이 화면 안에 있다', '영수증 팝업이 화면 밖으로 나갔다');
        /* 열어 놓고 「이 줄이 맞나」 를 보는 자리라 **예산 항목과 금액**이
           함께 서야 한다 (7-4) — 없으면 표로 눈을 다시 옮겨야 한다. */
        /* **값까지 본다** — 「영수증 금액 원」 처럼 이름만 남아도 라벨은
           그대로라, 낱말만 찾으면 빈 값이 안 걸린다 */
        잰다(/영수증 금액 [\d,]+원/.test(팝.textContent),
             ' 팝업이 예산 항목과 금액을 함께 낸다', '영수증 팝업에 금액 값이 없다');
        const 추가 = 팝.querySelector('.rcptmore'), 삭제 = 팝.querySelector('.rcptdel');
        잰다(!!추가 === !!고칠수있는줄 && !!삭제 === !!고칠수있는줄,
             ` 추가·삭제가 권한과 맞는다 (${고칠수있는줄 ? '고칠 수 있는 줄' : '못 고치는 줄'})`,
             '영수증 팝업의 추가·삭제가 권한과 어긋난다');
      }
      await 팝닫기();
    }

    /* **영수증이 없는 줄에는 「영수증 추가」 가 없다** (막는 쪽 · 7-4) —
       거기서 하는 것은 새로 올리는 것뿐이고, 번호로 잇는 것은 이미 있는
       영수증의 팝업에서 한다. */
    const 빈줄 = 줄들().find(tr => !tr.querySelector('.rcptchip')
                              && tr.querySelector('.rcptadd'));
    if (!빈줄) results.push('· 영수증이 없는 줄이 없어 「+ 첨부」 갈래는 건너뜀');
    else {
      빈줄.querySelector('.rcptadd').click();
      await 될때까지('올리기 팝업', () => !!document.querySelector('.exppop.rcptpop'));
      const 팝 = document.querySelector('.exppop.rcptpop');
      잰다(!!팝 && !팝.querySelector('.rlink'),
           ' 영수증 없는 줄의 「+ 첨부」 는 올리기뿐이다',
           '영수증이 없는 줄인데 「번호로 잇기」 가 떴다');
      await 팝닫기();
    }
  }

  /* ── 끝까지 돌았는가 ────────────────────────────────────────────
     한복판에서 죽으면 그때까지 잰 것만 남아 「전부 통과」 로 보인다 —
     밖에서 받아 `완주: false` 로 적는다(`drawer.js` 와 같은 자리). */
  const 완주 = true;
  const 잰것 = results.filter(r => /^[✓✗]/.test(r)).length;
  const 건너뜀 = results.filter(r => String(r).startsWith('·')).length;
  if (건너뜀) results.push(`· 이 계정·이 화면에서 안 재진 항목 ${건너뜀}개 — `
    + (고칠수있나 ? '**부서 리더**' : '**관리자**') + ' 계정으로 한 번 더 돌려 보세요');
  if (못쟀음.length) results.push(`? 못 쟀음 ${못쟀음.length}개 — 화면이 틀린 것이`
    + ' 아니라 이 판에서 답을 못 얻은 것입니다 (탭을 보이게 두고 다시 돌리세요)');
  console.table(results);
  return {화면: where, 폭, 호버있나, 통과: errors.length === 0 && 완주, 완주,
          실패: errors, 항목수: 잰것, 건너뜀, 못쟀음, 항목: results};
};

/* ── 자가시험 — 고장을 심어서 검사를 검사한다 ───────────────────────
   갈래마다 고장을 하나씩 심었다 걷어내며 **✗ 로 나오는지** 잽니다.
   통과나 「못 쟀음」 으로 나오면 거기가 검사가 새는 입구입니다.

   **`나와야` 는 항목의 라벨이다** — 실패 문구가 아니다. 자가시험은 `✗` 로
   시작하는 줄에서 찾는데 그 줄에 실리는 것이 라벨이다(`phone.js` 가
   2026-09-13 에 이 둘을 「놓침」 으로 잡아 알아낸 자리). */
const 스타일 = css => {
  const s = document.createElement('style');
  s.textContent = css;
  document.head.appendChild(s);
  return () => s.remove();
};
const 캡처막기 = (골라, 무엇 = 'click') => {
  const f = e => { if (e.target instanceof Element && 골라(e.target)) e.stopPropagation(); };
  document.addEventListener(무엇, f, true);
  return () => document.removeEventListener(무엇, f, true);
};

const 고장들 = [
  /* **스타일로는 못 심는다** — 보는 판에는 핸들이 **아예 없다**(편집을 켤 때
     `budget.js` 가 그린다). 없는 것을 보이게 해도 아무 일이 없어 자가시험이
     「놓침」 으로 나왔다(2026-09-26 에 실제로 그랬다). 그래서 **넣어서** 심는다. */
  {갈래: '① 편집을 꺼도 핸들이 보인다', 화면: '예산',
   나와야: '편집이 꺼져 있으면 고치는 자리가 안 보인다',
   심는다: () => {
     const 칸 = document.querySelector('#budtbl tbody td.l3');
     if (!칸) return () => {};
     const 손잡이 = document.createElement('span');
     손잡이.className = 'grip';
     손잡이.dataset.grip = 'row';
     손잡이.textContent = '⠿';
     칸.prepend(손잡이);
     /* **넣기만 해도 안 보인다** — `.budtbl .grip` 은 기본이 `display:none`
        이고 `.budtbl.editing .grip` 만 켠다. 그 한정을 잃는 것이 곧 이
        회귀이므로, 넣는 것과 켜는 것을 **함께** 심는다(둘 중 하나만 심으면
        자가시험이 「놓침」 으로 나온다 — 두 번 다 그렇게 나왔다). */
     const 걷기 = 스타일('.budtbl .grip{display:inline-block!important}');
     return () => { 손잡이.remove(); 걷기(); };
   }},
  {갈래: '② 「전체 편집」 이 안 먹는다',
   나와야: '「전체 편집」 을 누르면 표가 편집 상태가 된다',
   못심음: 항목 => 항목.some(r => String(r).includes('「전체 편집」 이 없어')),
   심는다: () => 캡처막기(el => !!el.closest('.editall'))},
  {갈래: '③ 끌어다 놓아도 차례가 그대로', 화면: '예산',
   나와야: '세부항목을 끌어다 놓으면 차례가 바뀐다',
   못심음: 항목 => 항목.some(r => String(r).includes('끌어 옮길 줄이')
                          || String(r).includes('「전체 편집」 이 없어')),
   심는다: () => 캡처막기(el => !!el.closest('.grip'), 'dragstart')},
  {갈래: '④ 소계 제목이 엉뚱한 칸에 붙는다', 화면: '예산',
   나와야: '「소계」 제목이 예산금액 바로 왼쪽이다',
   심는다: () => {
     const 칸들 = [...document.querySelectorAll('tr.subtot td.r')];
     const 원래 = 칸들.map(td => td.colSpan);
     칸들.forEach(td => td.colSpan = 5);
     return () => 칸들.forEach((td, i) => td.colSpan = 원래[i]);
   }},
  {갈래: '⑤ 줄을 더해도 안 는다', 화면: '예산',
   나와야: '「+ 줄 추가」 로 줄이 하나 는다',
   못심음: 항목 => 항목.some(r => String(r).includes('「+ 줄 추가」 가 없어')
                          || String(r).includes('「전체 편집」 이 없어')),
   심는다: () => 캡처막기(el => !!el.closest('#budadd'))},
  {갈래: '⑥ 편집 중에 콤마가 안 붙는다', 화면: '예산',
   나와야: '편집 중에도 천 단위 콤마',
   못심음: 항목 => 항목.some(r => String(r).includes('콤마는 건너뜀')
                          || String(r).includes('「전체 편집」 이 없어')),
   심는다: () => 캡처막기(el => !!(el.dataset && el.dataset.f), 'input')},

  /* **여백으로는 못 심는다** — 칸 안의 여백은 표의 오른쪽 끝을 안 옮긴다.
     이 회귀는 **병합 수가 그려질 줄 수와 어긋나는 것**이므로(검토 [C]) 그대로
     심는다: 걸친 줄 수를 하나 줄이면 그 아래가 통째로 밀린다. */
  {갈래: '⑦ 줄마다 칸이 밀린다', 화면: '지출',
   나와야: '줄마다 칸이 머리글과 같다',
   못심음: () => !document.querySelector('.exptbl td.catcell[rowspan]')
     || [...document.querySelectorAll('.exptbl td.catcell')].every(td => td.rowSpan < 2),
   심는다: () => {
     const 칸들 = [...document.querySelectorAll('.exptbl td.catcell, .exptbl td.l3b')]
       .filter(td => td.rowSpan > 1);
     const 원래 = 칸들.map(td => td.rowSpan);
     칸들.forEach(td => td.rowSpan = td.rowSpan - 1);
     return () => 칸들.forEach((td, i) => td.rowSpan = 원래[i]);
   }},
  {갈래: '⑧ 긴 내용 팝업이 안 뜬다', 화면: '지출',
   나와야: '긴 내용을 누르면 팝업이 뜬다',
   못심음: 항목 => 항목.some(r => String(r).includes('긴 내용(명단')),
   심는다: () => 캡처막기(el => !!el.closest('.longcell'))},
  {갈래: '⑨ 팝업이 화면 밖으로 나간다', 화면: '지출',
   나와야: '긴 내용 팝업이 화면 안에 있다',
   못심음: 항목 => 항목.some(r => String(r).includes('긴 내용(명단')),
   심는다: () => 스타일('.exppop{left:-400px!important}')},
  /* **전파를 막아서는 못 심는다** — 팝업의 닫는 줄이 먼저 걸려 있어 이미
     돌아간 뒤다. 이 회귀는 **「여기가 팝업 안인가」 판정이 너무 넓어지는
     것**이므로 그대로 심는다: 바깥의 무엇을 눌러도 팝업 안으로 읽히게 한다. */
  {갈래: '⑩ 바깥을 눌러도 안 닫힌다', 화면: '지출',
   나와야: '바깥을 누르면 팝업이 닫힌다',
   못심음: 항목 => 항목.some(r => String(r).includes('긴 내용(명단')),
   심는다: () => {
     document.body.classList.add('exppop');
     return () => document.body.classList.remove('exppop');
   }},
  {갈래: '⑪ 계좌 팝업에 복사가 없다', 화면: '지출',
   나와야: '계좌 팝업에 「복사」 가 있다',
   못심음: 항목 => 항목.some(r => String(r).includes('계좌가 적힌 지출이 없거나')),
   심는다: () => 스타일('.acctcopy{display:none!important}')},
  {갈래: '⑫ 영수증 팝업에 금액이 없다', 화면: '지출',
   나와야: '팝업이 예산 항목과 금액을 함께 낸다',
   못심음: 항목 => 항목.some(r => String(r).includes('영수증이 걸린 지출이 없어')),
   심는다: () => {
     const 줄들 = [...document.querySelectorAll('tr[data-exp][data-amount]')];
     const 원래 = 줄들.map(tr => tr.dataset.amount);
     줄들.forEach(tr => tr.dataset.amount = '');
     return () => 줄들.forEach((tr, i) => tr.dataset.amount = 원래[i]);
   }},
  {갈래: '⑬ 영수증 없는 줄에 「번호로 잇기」 가 뜬다', 화면: '지출',
   나와야: '영수증 없는 줄의 「+ 첨부」 는 올리기뿐이다',
   못심음: 항목 => 항목.some(r => String(r).includes('영수증이 없는 줄이 없어')),
   /* **`.rcptadd` 를 없애는 것으로는 못 심는다** — 점검이 그 이름으로
      빈 줄을 찾으므로, 이름을 바꾸면 찾을 줄이 사라져 **건너뜀**이 되고
      갈래는 영영 「놓침」 이다(2026-09-26 커밋 전 검토 [C]). 재려는 것은
      「그 팝업에 번호로 잇기가 떴는가」 이므로 **팝업 쪽**에 심는다. */
   심는다: () => {
     const 고친다 = () => document.querySelectorAll('.exppop.rcptpop').forEach(팝 => {
       if (팝.querySelector('.rlink')) return;   // 자기 쓰기를 다시 듣지 않게
       const b = document.createElement('button');
       b.type = 'button'; b.className = 'rlink'; b.textContent = '번호로 잇기';
       팝.appendChild(b);
     });
     const mo = new MutationObserver(고친다);
     mo.observe(document.body, {childList: true, subtree: true});
     고친다();
     return () => {
       mo.disconnect();
       document.querySelectorAll('.exppop.rcptpop .rlink').forEach(b => b.remove());
     };
   }},
  /* **막는 판정 자체를 지운다** — 팝업은 표의 `editing` 클래스로 편집 중인지
     보므로, 누르는 순간 그 클래스를 걷으면 옛 동작(그대로 열림)이 된다.
     고친 자리를 되돌려 심는 것이 가장 정확하다(`phone.js` ① 의 그 방식). */
  {갈래: '⑭ 편집 중에 팝업이 그대로 열린다', 화면: '지출',
   나와야: '편집 중에는 팝업 대신 까닭을 말한다',
   못심음: 항목 => 항목.some(r => String(r).includes('편집 중 팝업 막기')
                          || String(r).includes('「전체 편집」 이 없어')),
   심는다: () => {
     const 표 = document.querySelector('table.exptbl');
     const f = e => {
       if (e.target instanceof Element && e.target.closest('.longcell') && 표) {
         표.classList.remove('editing');            // 팝업이 「편집 중」 을 못 보게
       }
     };
     document.addEventListener('click', f, true);
     return () => document.removeEventListener('click', f, true);
   }},
];

/* **판마다 자리를 고르고 시작한다.** 앞 갈래가 편집을 켠 채 끝나면 다음
   판이 그 자국 위에서 돌아 **심지 않은 고장이 섞인다**(`phone.js` 의 그
   교훈). 여는 길이 아니라 **판을 고르는 일**이라 단추를 직접 누르고
   여기서만 시간을 기다린다 — 재는 자리가 아니라 치우는 자리다. */
const 판정리 = async () => {
  document.querySelectorAll('.exppop').forEach(p => p.remove());
  for (const [표id, 되돌림id] of [['budtbl', 'budcancel'], [null, 'expcancel']]) {
    const 표 = 표id ? document.getElementById(표id) : document.querySelector('table.exptbl');
    if (!표 || !표.classList.contains('editing')) continue;
    const b = document.getElementById(되돌림id);
    if (b) b.click();
    const 끝 = Date.now() + 1500;
    while (표.classList.contains('editing') && Date.now() < 끝) await sleep(25);
  }
};

const 자가시험 = async () => {
  await 판정리();
  const 깨끗 = await 점검();
  if (깨끗.치명) return 깨끗;
  const 줄 = [];
  /* **안 심었을 때 초록인 것도 같은 판에서 본다** — 늘 빨간 검사는
     아무것도 안 재는 검사와 같다(11-3 의 둘째 축). */
  줄.push((깨끗.통과 ? '✓' : '✗') + ' 안 심으면 초록'
          + (깨끗.통과 ? '' : ` — 실패: ${깨끗.실패.join(' / ')}`));
  let 잡음 = 0, 놓침 = 0, 못심음 = 0;
  for (const 것 of 고장들) {
    /* **다른 화면의 갈래는 못 심음이다** — 예산에서 지출 갈래를 심으면
       심을 자리가 아예 없다. 「안 해 봤다」 가 아니라 「그 화면에 없다」 라
       이유가 되는 자리다(11-3). */
    if (것.화면 && 것.화면 !== 깨끗.화면) {
      못심음++;
      줄.push(`- ${것.갈래} — ${깨끗.화면} 화면에는 그 자리가 없어 **못 심음**`);
      continue;
    }
    if (것.못심음 && 것.못심음(깨끗.항목)) {
      못심음++;
      줄.push(`- ${것.갈래} — 이 계정에 그 자리가 없어 **못 심음**`);
      continue;
    }
    await 판정리();
    const 걷기 = 것.심는다();
    let 결과;
    try { 결과 = await 점검(); } finally { if (typeof 걷기 === 'function') 걷기(); await 판정리(); }
    const 잡았나 = !결과.치명
      && (결과.항목 || []).some(r => String(r).startsWith('✗') && String(r).includes(것.나와야));
    if (잡았나) { 잡음++; 줄.push(`✗ ${것.갈래} — 잡음`); }
    else { 놓침++; 줄.push(`! ${것.갈래} — **놓침** (심었는데 ✗ 가 안 났다)`); }
  }
  console.table(줄);
  return {자가시험: true, 화면: 깨끗.화면, 잰것: 잡음, 놓친것: 놓침, 못심음,
          안심으면초록: 깨끗.통과, 줄};
};

/* **죽은 채로 「통과」 를 내지 않는다.** 중간에 예외가 나면 여기서 받아
   `완주: false` 로 돌려준다 — 콘솔에 빨간 줄만 남고 결과가 없으면, 돌린
   사람은 「안 돌았다」 와 「돌았는데 초록」 을 구별하지 못한다. */
const 지킨다 = p => p.catch(e => ({완주: false, 통과: false,
  실패: ['점검이 중간에 죽었습니다: ' + (e && e.message ? e.message : e)]}));

return 지킨다(window.__자가시험 ? 자가시험() : 점검());
})()
