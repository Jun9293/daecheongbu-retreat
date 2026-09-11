/* 상세 패널 상호작용 점검 — CLAUDE.md 10장의 규칙을 실제로 돌리는 스크립트.
 *
 * 쓰는 법: **보드(/board) · 달력(/calendar) · 목록(/tasks)** 을 연 뒤 브라우저
 * 콘솔에 이 파일 내용을 붙여넣습니다. 화면을 고쳤으면 "됐다"고 말하기 전에 돌립니다.
 *
 * **세 화면에서 각각 돌립니다.** 패널은 한 벌이지만(templates/partials/drawer.html ·
 * static/js/drawer.js), 그것을 여는 자리와 고쳐 그리는 코드는 화면마다 다릅니다.
 * 한쪽만 통과하면 패널이 실제로는 한 벌이 아니라는 뜻입니다 (CLAUDE.md 4-13 · 4-14).
 *
 * **그리고 두 계정으로 돌립니다 — 관리자와 부서 리더.** 관리자에게는 모든
 * 행이 「바꿀 수 있음」 이라 **못 바꾸는 쪽이 아예 안 재집니다.** 반대로
 * 부서 리더로는 고칠 수 있는 쪽이 덜 재집니다. 끝에 나오는 **건너뜀 수**가
 * 그것을 말하고, 0 이 아니면 어느 계정으로 다시 돌라고 함께 적습니다.
 *
 * **어느 회차를 열지 정해서 들어갑니다 — `?retreat_id=<id>`.**
 * 안 붙이면 기본 회차가 열리는데, 그것은 「보관 안 된 것 중 개회일이 가장
 * 늦은 것」 입니다(`app/deps.py`). 2026-09-12 현재 그것은 **2027 회차**이고,
 * 그 회차는 **열 자리가 적습니다** — 업무는 백 건 넘게 있어도 논의·첨부·
 * 선후행이 아직 안 쌓여서, 이 점검의 항목 상당수가 「건너뜀」 으로 빠집니다.
 * **건너뛴 항목도 항목 수에 들어가므로 「N/N 통과」 가 뜻을 잃습니다.**
 *
 * 그래서 지금은 **2026 회차(`?retreat_id=1`)** 로 돌립니다 — 실제로 쓰인
 * 회차라 논의도 첨부도 선후행도 있습니다.
 *
 * **`?retreat_id=` 는 읽기만 하는 길이 아닙니다.** `app/deps.py` 가 그
 * 주소를 받으면 **그 계정의 「보던 회차」 를 거기로 바꿔 저장합니다**
 * (`remember_retreat`). 그래서 한 번 열고 나면 파라미터 없이 들어와도
 * 그 회차가 뜹니다 — 위의 「안 붙이면 기본 회차가 열린다」 는 **저장된
 * 회차가 없는 계정에만** 맞는 말입니다.
 *
 * **점검을 돌린 계정은 돌린 뒤 되돌려 두세요** — 회차 드롭다운에서 원래
 * 보던 회차를 다시 고르면 됩니다. 남의 계정으로 돌렸다면 그 사람이 다음에
 * 열 때 지난 회차가 뜨고 **왜인지 모릅니다.**
 *
 * **그래서 되도록 개발 서버에서 돌립니다** — 운영 계정의 보던 회차를
 * 건드리지 않습니다.
 *
 * **언제 바꾸나** — 2027 에 실제 자료가 쌓여 건너뜀이 줄면 그때 그쪽으로
 * 옮깁니다. 판단은 **회차 번호가 아니라 건너뜀 수**로 합니다: 같은 화면·
 * 같은 계정에서 건너뜀이 2026 쪽보다 많지 않으면 옮길 때입니다.
 * 회차 id 를 여기 박아 두지 않는 이유도 그것입니다 — 이 주석이 말하는 것은
 * 「1 을 써라」 가 아니라 **「자료가 있는 회차를 골라라」** 입니다.
 *
 * 탭이 화면에 보이는 상태에서 돌립니다. 배경 탭에서는 브라우저가 타이머를
 * 1초 단위로 묶어 버려 중간에 끊깁니다 — 페이지가 멈춘 것이 아닙니다.
 *
 * **느리다고 시간을 줄이거나 타이머를 대체하지 마세요. 세 판 연속
 * 그렇게 흔들렸습니다.** 타이머를 마이크로태스크로 바꿨다가 한 채널에
 * 콜백을 덮어써 sleep 이 서로를 지웠고, 250ms 를 기다렸는데 아직 안
 * 닫혀서 다음 클릭이 토글이 됐고, 대기가 접혀 레이아웃 전에 스냅샷을
 * 찍었습니다 — 셋 다 **화면이 아니라 검사가 흔들린 것**입니다.
 * 검사가 흔들리면 그 결과로는 아무것도 못 정합니다.
 *
 * 그래서 이제 **기다리지 않고 봅니다** — 「얼마쯤 기다린다」 가 아니라
 * 「메뉴가 닫힌 것을 보고 간다」. 상한에 걸린 항목은 ✗ 가 아니라
 * **「못 쟀음」**(`?`)으로 나옵니다. 느리면 **탭을 보이게** 하세요 —
 * 상한을 항목마다 늘리는 손잡이는 일부러 두지 않았습니다.
 *
 * **다만 「못 쟀음」 은 주변이 멀쩡할 때만입니다.** 기다리던 것이 안
 * 나타난 이유가 「그 클릭이 드로어를 닫아서」 이면 그건 검사가 못 잰
 * 것이 아니라 **화면이 무너진 것**이라 ✗ 로 나옵니다.
 *
 * **✗ 를 찍는 길은 `잰다` 하나입니다.** 찍는 것과 세는 것을 따로 두면
 * 손으로 맞춰야 하고, 실제로 셋이 어긋나 ✗ 인데도 「통과」 였습니다.
 *
 * **콘솔에 붙여넣는 대신 서버에서 받아 돌릴 때** — 이 파일을
 * `app/static/` 에 사본으로 두고 `fetch` 하는 길이 있는데, 정적 주소가
 * **내용 해시라 1년 immutable** 입니다(11-2). 그래서 사본을 고치고 같은
 * 주소로 다시 받으면 **옛 것이 옵니다.** 주소의 해시 자리를 매번 바꾸고
 * `{cache: 'reload'}` 로 받은 뒤, **받은 길이를 찍어** 지금 파일과 같은지
 * 보세요. 2026-09-09 에 이걸 안 해서 고친 줄이 안 실린 채로 여섯 판을
 * 돌렸고, 길이를 찍어 보고서야 알았습니다.
 *
 * **자가시험 — 검사가 볼 것을 실제로 보는지 검사가 스스로 증명합니다.**
 * 갈래마다 고장을 하나씩 심었다 걷어내며 그것이 ✗ 로 나오는지 잽니다.
 * 평소 점검과 따로 돌아 평소가 느려지지 않습니다 — 붙여넣기 **전에**
 * `window.__자가시험 = 1;` 을 실행하세요. **이 파일을 고친 판에서는
 * 반드시, 그리고 두 계정으로 돌립니다** (11-3 2단계) — 부서 리더에게는
 * 못 심는 갈래가 있고, 그때 ✗ 가 아니라 **「못 심음」** 으로 나오는 것이
 * 그쪽의 정답입니다. 자세한 것은 파일 끝의 그 자리에.
 *
 * 무엇을 보는가 — 각 조작이 '되는가'만이 아니라, 그 뒤에도 주변이 그대로인가.
 *   · 드로어가 열려 있는가 (패널 안의 버튼은 패널을 닫지 않는다)
 *   · 보던 자리가 그대로인가 (보드는 부서 그룹, 달력은 보던 달과 칩)
 *   · 스크롤이 그대로인가 (이동은 명시적으로 요청했을 때만)
 * 보임/숨김은 속성이 아니라 offsetParent 로 판정한다 — el.hidden 은 거짓말을 한다.
 */
(async () => {
const 점검 = async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const $ = id => document.getElementById(id);
  const dw = $('drawer');
  const shown = el => !!(el && el.offsetParent);
  const painted = el => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== 'none' && r.width > 0 && r.height > 0; };
  const errors = [], results = [], 못쟀음 = [];

  /* ── 찍는 자리와 세는 자리는 하나다 ───────────────────────────────
     **✗ 를 찍는 길이 여기 하나뿐이다.** 전에는 `results.push` 로 찍고
     그 다음 줄에서 `errors.push` 로 세었는데, 둘을 **손으로 맞춰야**
     했고 실제로 셋이 어긋나 있었다 — ✗ 를 찍고도 안 세어서 그 줄이
     빨개져도 `통과: true` 였다(2026-09-09 검토). 갈래 단위인 자가시험은
     그 틈을 못 본다(봐둘것 AI-d).

     그래서 둘을 한 함수로 모았다. `까닭` 을 안 주면 라벨을 그대로
     쓴다 — 「✗ 를 찍었는데 셀 말이 없다」 가 생기지 않게.
     JS 에서 배열을 진짜로 숨길 수는 없으므로 **검사가 견준다** —
     `tests/test_stage20.py` 가 ✗ 를 찍는 줄과 세는 줄이 **각각 하나**
     인지 본다. 둘이 되는 순간 손으로 맞추는 자리가 다시 생긴 것이다. */
  const 잰다 = (ok, 라벨, 까닭) => {
    results.push((ok ? '✓' : '✗') + 라벨);
    if (!ok) errors.push(까닭 === undefined ? 라벨.trim() : 까닭);
    return ok;
  };

  /* ── 기다리지 말고 본다 ───────────────────────────────────────────
     시간을 어림으로 박으면 **검사가 흔들립니다.** 세 판 연속 그랬고
     셋 다 같은 모양이었습니다 — 250ms 를 기다렸는데 아직 안 닫혀서
     다음 클릭이 토글이 되고, 대기가 접혀 레이아웃 전에 스냅샷을 찍고,
     타이머를 대체했더니 콜백이 서로를 지웠습니다.

     그래서 **바뀔 것을 보고 갑니다.** 상한은 두되(무한정 기다리지
     않는다) 상한에 걸린 항목은 **✗ 가 아니라 「못 쟀음」** 입니다 —
     검사가 흔들린 것과 화면이 고장 난 것을 가릅니다. ✗ 는 화면이
     틀렸다는 말이고, 「못 쟀음」 은 이 판에서 답을 못 얻었다는 말입니다.

     **단, 주변이 무너졌으면 못 쟀음이 아니라 ✗ 입니다** — 기다리던
     것이 안 나타난 이유가 그 회귀일 수 있기 때문입니다(`check` 참조). */
  // 상한은 **하나**다 — 항목마다 다른 값을 주는 길을 두지 않는다
  const 상한기본 = 3000;
  /* **안 되는 것이 답인 자리**는 「못 쟀음」 이 아니다. 「닫혀야 하는데
     안 닫힌다」 는 화면의 고장이므로 ✗ 로 세야 한다 — 그 자리는 이것을
     쓴다(상한까지 보고 그대로 돌려준다). */
  const 잠깐본다 = async (조건, 상한 = 1200) => {
    const 끝 = Date.now() + 상한;
    for (;;) {
      let ok = false;
      try { ok = !!조건(); } catch (e) { ok = false; }
      if (ok || Date.now() >= 끝) return ok;
      await sleep(25);
    }
  };

  /* `적는다` 를 끄면 못쟀음 에 안 담고 결과만 돌려준다 — `check` 가
     주변을 마저 재고 **✗ 인지 못 쟀음인지 스스로 정하기** 위해서다.
     여기서 먼저 담아 버리면 ✗ 로 판정된 것까지 못 쟀음에 남아 두 번 센다. */
  const 될때까지 = async (무엇, 조건, 상한 = 상한기본, 적는다 = true) => {
    const 끝 = Date.now() + 상한;
    for (;;) {
      let ok = false;
      try { ok = !!조건(); } catch (e) { ok = false; }
      if (ok) return true;
      if (Date.now() >= 끝) { if (적는다) 못쟀음.push(무엇); return false; }
      await sleep(25);
    }
  };

  if (!dw) return {치명: '이 화면에는 상세 패널이 없습니다 (/board · /calendar · /tasks 에서 돌리세요)'};

  /* ── 어느 화면인가 ────────────────────────────────────────────────
     패널은 같지만 "무엇을 눌러 여는가" 와 "보던 자리가 무엇인가" 는 다르다.
     보드는 바와 부서 그룹, 달력은 점과 보던 달, 목록은 행의 펼침이다 (4-14). */
  const sheet = $('sheet'), board = $('board');
  const tlist = $('tlist');
  const calbar = document.querySelector('.calbar');
  const isBoard = !!(sheet && board);
  const isList = !isBoard && !!tlist;
  const where = isBoard ? '보드' : isList ? '목록' : '달력';
  const scroller = isBoard ? board
    : isList ? document.scrollingElement
    : (document.querySelector('.calwrap') || document.scrollingElement);

  const openers = () => isBoard
    ? [...sheet.querySelectorAll('.bar[data-run]')].filter(b => shown(b) && !b.dataset.ghost)
    : isList
    // **행 전체가 여는 자리다** (4-14) — 이름은 그중 한 곳일 뿐이다.
    // 여는 자리 목록이 아니라 안 여는 자리 목록이므로, 여기서는 행을 연다
    ? [...document.querySelectorAll('.trow.lrow')].filter(shown)
    : [...document.querySelectorAll('.cal-dot[data-run]')].filter(shown);

  const snapshot = () => ({
    drawer: dw.classList.contains('open'),
    // 보던 자리 — 보드는 펼쳐진 부서 수, 달력은 보이는 점, 목록은 보이는 행
    kept: isBoard
      ? [...sheet.querySelectorAll('.row.team')].filter(t => !t.classList.contains('collapsed')).length
      : isList
      ? [...document.querySelectorAll('.trow.lrow')].filter(shown).length
      : openers().length,
    scroll: Math.round(scroller.scrollTop),
    // 달력은 보던 달과 칩이 그대로여야 한다
    month: calbar ? calbar.dataset.month : '',
    chips: calbar ? calbar.dataset.scope + '/' + calbar.dataset.onlyOpen : '',
  });

  const check = async (label, act, opts = {}) => {
    const before = snapshot();
    await act();
    /* `until` 이 있으면 **그것이 될 때까지** 본다. 없으면 시간을 쓰되,
       그 자리는 「아무 일도 안 일어나는 것을 보는 자리」 라 기다릴
       상태가 없다는 뜻이다(부르는 쪽에 이유가 적혀 있다).

       **상한을 항목마다 따로 주는 길은 두지 않는다.** 느릴 때 돌릴
       손잡이가 있으면 그것을 돌려서 넘어가게 되고, 그러면 「못 쟀음」
       이 새는 자리가 된다 — 이 판이 없애려던 바로 그 모양이다.
       느리면 **탭을 보이게** 한다(머리말). */
    let 못쟀나 = false;
    if (opts.until) {
      못쟀나 = !(await 될때까지(label, opts.until, 상한기본, false));
    } else {
      /* **`until` 이 없는 자리는 「아무 일도 안 일어나는 것」 을 본다** —
         드롭다운을 눌러도 DOM 이 안 바뀌고, 드래그의 답은 「드로어가
         그대로 열려 있다」 다. 기다릴 신호가 없으므로 시간을 쓰되,
         **여기 말고 다른 곳에 시간을 두지 않는다.** */
      await sleep(opts.wait || 420);
    }
    const after = snapshot();
    const bad = [];
    if (!opts.mayClose && before.drawer && !after.drawer) bad.push('드로어가 닫힘');
    if (!opts.mayCollapse && after.kept < before.kept) bad.push(isBoard ? '부서 그룹이 접힘' : '점이 사라짐');
    if (!opts.mayScroll && Math.abs(after.scroll - before.scroll) > 4) bad.push('스크롤이 움직임');
    if (after.month !== before.month) bad.push('보던 달이 바뀜');
    if (after.chips !== before.chips) bad.push('범위 칩이 바뀜');

    /* **못 쟀어도 주변은 잰다.** 전에는 상한에 걸리면 곧바로
       빠져나갔는데, 그러면 **클릭이 드로어를 닫아 버린 진짜 회귀가
       ✗ 가 아니라 「못 쟀음」 으로** 나온다 — 기다리던 것이 안 나타난
       이유가 바로 그 회귀인데도. 10장의 그 표(드로어·부서 그룹·
       스크롤·보던 달·범위 칩)는 여기서 건너뛰면 안 되는 것이다.
       **주변이 무너졌으면 ✗ 다.** 주변이 멀쩡한데 기다린 것만 안
       나타났을 때가 「못 쟀음」 — 그때는 검사가 엉뚱한 것을 기다린
       것이다 (봐둘것 AH-b). */
    if (bad.length) {
      잰다(false, ` ${label}`, label + ' → ' + bad.join(', ')
        + (못쟀나 ? ' (기다린 것도 안 나타났다 — 주변이 무너져서다)' : ''));
      return;
    }
    if (못쟀나) {
      못쟀음.push(label);
      results.push(`? ${label} — 못 쟀음 (주변은 그대로인데 기다린 것이 안 나타남)`);
      return;
    }
    잰다(true, ` ${label}`);
  };

  /* **없는 것을 누르지 않는다.** 고칠 수 없는 업무를 연 계정에서는
     담당자·담당팀·시작일 칸이 아예 안 그려진다 — 그냥 누르면 검사가
     `null.click()` 으로 **죽고**, 그러면 그 계정에서는 아무것도 안
     재진다(2026-09-08 판에서 부서 리더로 돌리자 보드가 그렇게 멈췄다).
     안 재는 것은 안 재는 것으로 적는다 — 건너뜀 수에 들어간다. */
  /* **여기는 기다릴 상태가 없다.** 이 자리들이 누르는 것은 드롭다운·
     체크박스·입력칸이라 **눌러도 DOM 이 안 바뀝니다** — 재는 것은
     「그래도 드로어가 열려 있는가」(10장의 그 표)이고, 그건 아무 일도
     안 일어나는 것을 보는 일이라 기다릴 신호가 없습니다. 그래서
     `check` 의 기본 대기를 그대로 씁니다. */
  /* **죽었는지 보는 곳은 여기 하나다.** 없는 것(`null`) · 안 그려진 것
     (`offsetParent` 가 없다) · 죽어 있는 것(`disabled`) 셋을 한 자리에서
     본다. 저장소를 훑어 보니 앱이 실제로 `disabled` 로 두는 것은
     `#statchip`(권한)과 하단의 「하위 업무 추가」(Phase 2)뿐이고 뒤엣것은
     이 점검이 안 누른다 — 그래도 판정을 한 곳에 두는 이유는, 다음에
     죽는 단추가 생겨도 그 자리만 고치면 되기 때문이다. */
  const 살아있나 = el => !!(el && shown(el) && !el.disabled);

  /* **「열렸다」 는 「다 그려졌다」 가 아니다.** `openDrawer` 는 `open` 을
     먼저 붙이고 **그 다음에** 서버에 물어본다 — 그 사이에는 머리도
     권한 칩도 옛 것이거나 없다. 옛 코드가 900ms 를 기다린 것이 그것을
     덮고 있었는데, 「open 이 붙었나」 로만 바꾸자 **관리자로 돌면서도
     「권한과 어긋남」 이 다섯 줄** 났다(고쳐 놓고 바로 잡혔다).
     그래서 **불러오기가 끝난 것**을 본다 — 상태 칩이 그려지고
     「불러오는 중…」 이 사라진 때다. */
  const 열렸다 = () => dw.classList.contains('open') && !!$('statchip')
    && !($('dlog') || {}).textContent?.includes('불러오는 중');

  const 누른다 = async (라벨, el, opts = {}) => {
    if (살아있나(el)) return check(라벨, () => el.click(), opts);
    results.push(`· ${라벨} — 이 계정에는 그 칸이 없거나 죽어 있어 건너뜀`);
  };

  const 눌러본다 = async (라벨, id) => {
    const el = $(id);
    /* **죽어 있는 것도 안 누른다.** `statchip` 은 고칠 수 없는 계정에서도
       지워지지 않고 `disabled` 로 남는다 — 있고 보이기까지 하므로
       `shown` 만으로는 안 갈린다. 그냥 누르면 아무 이벤트도 안 나고
       「드로어가 안 닫혔다」 가 언제나 참이라 **✓ 가 그냥 붙는다**
       (검토가 짚었다 — 「센 것이 0이면 성공이 아니다」 의 같은 자리). */
    return 누른다(라벨, el);
  };

  /* ── 끝까지 돌았는가 ──────────────────────────────────────────────
     **점검이 통째로 죽으면 「전부 통과」 로 보입니다.** 2026-09-10 에
     같은 이름의 지역 변수 하나가 판정 줄을 가려 TDZ 오류를 냈고, 점검이
     한복판에서 죽어 결과 객체가 아예 안 나왔습니다(봐둘것 AJ-b).
     그때 알아본 것은 사람이지 출력이 아니었습니다.

     그래서 **출력이 스스로 말합니다** — 끝까지 갔으면 `완주: true`,
     중간에 죽었으면 `완주: false` 와 함께 그 자리가 ✗ 로 남습니다.
     죽어도 그때까지 잰 것은 그대로 돌려줍니다. */
  let 완주 = false;
  try {
    results.push(`· 돌린 화면: ${where} (${location.pathname})`);

    // 보드는 소속 필터를 전체로 두고 시작한다. 달력에는 그 칸이 없다.
    if (isBoard) {
      $('me').value = 'all'; $('me').dispatchEvent(new Event('change'));
      // 보드를 다시 그린다 — **다시 그려진 것을 보고 간다**
      await 될때까지('소속 필터를 전체로', () => openers().length > 0);
    }
    const 목표 = isBoard ? 220 : 0;
    scroller.scrollTop = 목표;
    await 될때까지('스크롤 자리 잡기', () => Math.abs(scroller.scrollTop - 목표) <= 2, 1500);

    const opener = openers()[0];
    if (!opener) return {치명: `${where} 에 열어 볼 업무가 하나도 없습니다`};
    opener.click();
    // **열린 것을 보고 간다.** 900ms 를 기다리던 자리다
    await 될때까지('첫 패널 열기', () => 열렸다());
    if (!dw.classList.contains('open')) return {치명: `${where} 에서 드로어가 열리지 않음`};
    results.push(`✓ ${isBoard ? '바' : isList ? '업무 이름' : '점'}을 눌러 그 자리에서 패널이 열림`);

    // 달력·목록이라면 **보드로 넘어가지 않았는지** 함께 본다
    if (!isBoard) {
      const stayed = location.pathname.startsWith(isList ? '/tasks' : '/calendar');
      잰다(stayed, ` 보드로 넘어가지 않음 (${location.pathname})`, '눌렀더니 보드로 넘어감');
    }

    // 목록 전용 (4-14) — 패널이 눌린 행 아래로 들어가고, 펼침이 주소에 남는다
    if (isList) {
      const slot = document.querySelector('.lslot:not([hidden])');
      const inline = !!(slot && slot.contains(dw) && dw.classList.contains('inline'));
      잰다(inline, ' 패널이 눌린 행 아래에서 펼쳐짐 (그 자리에서)', '패널이 행 아래로 들어가지 않음');
      const inUrl = new URLSearchParams(location.search).get('task');
      잰다(inUrl, ` 펼친 상태가 주소에 남음 (?task=${inUrl || '없음'})`, '펼친 상태가 주소에 안 남음');
      // 삭제 단추 없음 (4-9 · 0장) — 패널과 목록 어디에도
      const del = [...document.querySelectorAll('#drawer button, .tlist button')]
        .some(b => b.textContent.includes('삭제'));
      잰다(!del, ' 삭제 단추 없음', '삭제 단추가 있다');

      // 행의 칸 넷이 **보인다** — HTML 존재가 아니라 그려진 상태다 (단계 4).
      // offsetParent 와 크기, 그리고 빈 글자가 아님을 함께 본다.
      {
        const row = document.querySelector('.trow.lrow');
        const cells = [['부서/담당 없음', '.metaline .deptchip'],
                       ['담당자', '.metaline .asg, .metaline .deptchip:nth-child(2)'],
                       ['마감', '.metaline .due'],
                       ['배지', '.stbadge']];
        const bad = [];
        for (const [name, sel] of cells) {
          const el = row && row.querySelector(sel);
          const r = el && el.getBoundingClientRect();
          const visible = !!(el && el.offsetParent && r.width > 0 && r.height > 0
            && el.textContent.trim());
          if (!visible) bad.push(name);
        }
        잰다(bad.length === 0,
          ` 행에 칸 넷(부서·담당자·마감·배지)이 보임${bad.length ? ' — 안 보임: ' + bad.join(', ') : ''}`,
          '행의 칸이 화면에 안 보임: ' + bad.join(', '));
      }

      // ▸/▾ — 접었다 펴는 것임이 보인다. 캐럿은 행 오른쪽 끝이다 (4-14)
      {
        const cur = new URLSearchParams(location.search).get('task');
        const row = document.querySelector(`.trow.lrow[data-run="${cur}"]`);
        const openCaret = row && row.querySelector('.caret')?.textContent === '▾';
        const others = [...document.querySelectorAll('.trow.lrow')].filter(r => r !== row);
        const rest = others.every(r => r.querySelector('.caret')?.textContent === '▸');
        잰다(openCaret && rest, ' 펼친 행만 ▾, 나머지는 ▸', '▸/▾ 토글이 상태를 안 보여줌');
      }
    }

    /* **✗ 를 찍으면 반드시 센다.** 이 줄은 `errors.push` 가 없어서
       4-9 의 「열면 업무 규칙이 먼저 보입니다」 가 깨져도 `통과: true` 였다 —
       ✗ 가 화면에만 뜨고 결과에는 안 남는 자리다(검토가 셋을 짚었다). */
    {
      const 규칙탭 = document.querySelector('#dtabs [aria-selected=true]').dataset.p === 'rules';
      잰다(규칙탭, ' 처음 열면 업무 규칙 탭', '처음 열었는데 업무 규칙 탭이 아님');
    }

    // 제목 편집 (4-9) — Esc 는 **편집만** 취소한다. 전파가 새면 문서의 Escape
    // 핸들러가 드로어까지 닫는다 — 패널 안의 조작은 패널을 닫지 않는다 (10장)
    if (!document.querySelector('#statchip[disabled]') && $('dtitletext')) {
      const beforeTitle = $('dtitletext').textContent;
      await 누른다('제목 편집 열기', $('dtitletext'),
        {until: () => document.querySelector('#dtitletext input.titleedit')});
      const tinput = document.querySelector('#dtitletext input.titleedit');
      잰다(tinput, ' 제목 입력칸이 열림', '제목 입력칸이 열리지 않음');
      if (tinput) {
        await check('제목 편집 중 Esc (편집만 취소)', () => {
          tinput.dispatchEvent(new KeyboardEvent('keydown',
            {key: 'Escape', bubbles: true, cancelable: true}));
        });
        const restored = $('dtitletext').textContent === beforeTitle
          && !document.querySelector('#dtitletext input');
        잰다(restored, ' Esc 뒤 제목이 원래대로 (드로어는 그대로)', 'Esc 가 제목 편집을 취소하지 못함');
      }
    } else results.push('· 고칠 수 없는 업무라 제목 편집은 건너뜀');

    await check('탭 — 논의', () => $('dtabs').querySelector('[data-p="log"]').click(),
      {until: () => shown($('p-log'))});
    /* **권한으로 갈라서 잰다.** 논의 입력칸은 늘 열려 있어야 하지만(4-9)
       그것은 **고칠 수 있는 사람에게** 그렇다. 고칠 수 없는 업무를 연
       계정에서 「안 보인다」 를 고장으로 세면, 맞는 동작이 ✗ 로 난다 —
       상태 칸에서 배운 그 자리다(4-14). 못 고치는 쪽은 **안 보이는 것이
       맞다**로 뒤집어 잰다. */
    {
      const canEdit = !document.querySelector('#statchip[disabled]');
      const 보임 = shown($('daddlog'));
      const 맞나 = canEdit ? 보임 : !보임;
      잰다(맞나, ` 논의 입력칸이 ${보임 ? '보임' : '안 보임'} (고칠 수 ${canEdit ? '있음' : '없음'})`,
           '논의 입력칸이 권한과 어긋남');
    }

    await check('탭 — 업무 규칙', () => $('dtabs').querySelector('[data-p="rules"]').click(),
      {until: () => shown($('p-rules'))});
    if ($('drulesopen')) {
      await 누른다('규칙 편집 열기', $('drulesopen'),
        {until: () => shown($('drulesedit'))});
      잰다(shown($('drulesedit')), ' 규칙 편집창이 보임', '규칙 편집창이 보이지 않음');
      await 누른다('규칙 편집 취소', $('drulescancel'),
        {until: () => !shown($('drulesedit'))});
    }
    await check('탭 — 달력', () => $('dtabs').querySelector('[data-p="cal"]').click(),
      {until: () => shown($('p-cal'))});
    await check('탭 — 연결', () => $('dtabs').querySelector('[data-p="rel"]').click(),
      {until: () => shown($('p-rel'))});

    // 연결 탭 — 세 묶음 카드가 → 선행 · ← 후속 · ↔ 관련 순서다 (4-9)
    {
      const heads = [...document.querySelectorAll('#drel .relcard .rh')]
        .map(h => (h.querySelector('.arrow')?.textContent || '') + (h.querySelector('b')?.textContent || ''));
      const ok = heads.join(',') === '→선행,←후속,↔관련';
      잰다(ok, ` 연결 카드 셋이 순서대로 (${heads.join(' · ') || '없음'})`, '연결 카드가 세 묶음이 아니거나 순서가 다름');
    }

    // 확인 요청 (4-9) — 보내는 폼과 이력. 실제로 하나 보내 본다.
    await check('탭 — 확인 요청', () => $('dtabs').querySelector('[data-p="review"]').click(),
      {until: () => shown($('p-review'))});
    {
      const canEdit = !document.querySelector('#statchip[disabled]');
      const formOk = canEdit ? shown($('drevform')) : !shown($('drevform'));
      잰다(formOk, ` 확인 요청 폼 (편집 ${canEdit ? '가능' : '불가'})`, '확인 요청 폼이 권한과 어긋남');
      const firstDept = $('drevdepts') && $('drevdepts').querySelector('input');
      if (canEdit && firstDept) {
        const before = document.querySelectorAll('#drevlog .revitem').length;
        firstDept.checked = true;
        // **이력이 느는 것을 보고 간다** (서버 왕복이라 900ms 를 어림하던 자리)
        await 누른다('확인 요청 보내기', $('drevsend'),
          {until: () => document.querySelectorAll('#drevlog .revitem').length > before});
        const after = document.querySelectorAll('#drevlog .revitem').length;
        잰다(after > before, ` 보낸 요청이 이력에 남음 (${before} → ${after})`,
          '확인 요청이 이력에 안 남음');
      } else results.push('· 고를 부서가 없거나 편집 불가라 보내기는 건너뜀');
    }

    // 첨부파일 — 회차별. 탭을 옮기는 것도 '패널 안의 조작'이라 같은 기준으로 본다.
    await check('탭 — 첨부파일', () => $('dtabs').querySelector('[data-p="files"]').click(),
      {until: () => shown($('p-files'))});
    잰다(shown($('p-files')), ' 첨부파일 탭이 화면에 보임', '첨부파일 탭이 보이지 않음');
    {
      const tabs = [...document.querySelectorAll('#dtabs button')].map(b => b.dataset.p);
      const last = tabs[tabs.length - 1] === 'files';
      잰다(last, ` 첨부파일이 탭 맨 끝 (${tabs.join(' · ')})`, '첨부파일 탭이 맨 끝이 아님');

      // 드로어 폭에서 탭이 넘치지 않는가 — **첨부파일이 잘리면 안 된다**
      // (수를 적지 않는다 — 탭이 하나 늘면 그 수부터 낡는다: 10장)
      const bar = $('dtabs');
      /* **그려진 뒤에 잰다.** 드로어가 열리는 전환 중에는 폭이 0 이라
         `scrollWidth <= clientWidth` 가 언제나 거짓이고 「넘쳤다」 로 나온다 —
         화면이 아니라 **검사가 흔들린 것**이다. 실제로 페이지를 새로 연 뒤
         첫 판에서만 ✗ 가 났고 (157px / 0px), 같은 페이지에서 다시 돌리면
         드로어가 이미 열려 있어 통과했다. `열렸다()` 는 「불러오기가 끝났나」
         를 보지 **폭이 자리를 잡았나**를 보지 않는다.
         끝내 안 그려지면 그건 못 잰 것이지 넘친 것이 아니다 (머리말). */
      if (!await 될때까지('탭이 드로어 폭에 들어감', () => bar.clientWidth > 0)) {
        results.push('? 탭이 드로어 폭에 들어감 — 못 쟀음 (탭 바가 아직 안 그려짐)');
      } else {
        const fit = bar.scrollWidth <= bar.clientWidth + 1;
        const lastTab = [...bar.querySelectorAll('button')].pop();
        const inside = lastTab.getBoundingClientRect().right <= bar.getBoundingClientRect().right + 1;
        잰다(fit && inside, ` 탭이 드로어 폭에 들어감 (${bar.scrollWidth}px / ${bar.clientWidth}px)`,
             '탭이 넘쳐 첨부파일이 잘림');
      }

      // 올리는 자리는 탭 안에 있다. 고칠 수 없는 업무라면 없는 것이 맞다.
      const canEdit = !document.querySelector('#statchip[disabled]');
      const drop = shown($('ddrop'));
      const ok = canEdit ? drop : !drop;
      잰다(ok, ` 끌어다 놓는 자리 (편집 ${canEdit ? '가능' : '불가'})`, '올리는 자리가 권한과 어긋남');

      // 링크 붙이기도 같은 권한이다. 용량은 차지하지 않지만 자료인 것은 같다.
      const linkBtn = shown($('dlinkbtn'));
      const linkOk = canEdit ? linkBtn : !linkBtn;
      잰다(linkOk, ` 링크 붙이기 자리 (편집 ${canEdit ? '가능' : '불가'})`, '링크 붙이기가 권한과 어긋남');

      // 같은 기능이 두 군데 있으면 안 된다 — 하단의 '파일 첨부' 버튼은 없앴다
      const foot = [...document.querySelectorAll('.dfoot button')].map(b => b.textContent.trim());
      const clean = !foot.some(t => t.includes('파일 첨부'));
      잰다(clean, ` 하단에 '파일 첨부' 버튼 없음 (${foot.join(', ') || '없음'})`, "하단에 '파일 첨부' 버튼이 남아 있음");
    }
    await 눌러본다('첨부파일 — 올리는 자리 클릭', 'ddrop');

    // 링크 붙이기 — 폼을 열고, 틀린 주소를 넣어 보고, 닫는다.
    // **틀린 이유가 붙는 자리 바로 아래**에 나와야 한다.
    if (shown($('dlinkbtn'))) {
      await 누른다('링크 붙이기 열기', $('dlinkbtn'),
        {until: () => shown($('dlinkform'))});
      잰다(shown($('dlinkform')), ' 링크 붙이기 폼이 보임', '링크 붙이기 폼이 보이지 않음');
      await 누른다('링크 — 주소 칸 클릭', $('dlinkurl'));
      await check('링크 — 틀린 주소로 붙이기', () => {
        $('dlinkurl').value = '교개협 폴더';
        $('dlinkname').value = '';
        $('dlinksave').click();
      });
      const urlErr = shown($('dlinkurlerr')), nameErr = shown($('dlinknameerr'));
      잰다(urlErr, ' 주소가 아니면 그 자리에서 말함', '틀린 주소를 그냥 받음');
      잰다(nameErr, ' 설명을 비우면 그 자리에서 말함', '설명 없이 붙음');
      await 누른다('링크 붙이기 취소', $('dlinkcancel'),
        {until: () => !shown($('dlinkform'))});
      const 닫힘 = !shown($('dlinkform'));
      잰다(닫힘, ' 취소하면 폼이 닫힘', '링크 붙이기 폼이 취소해도 안 닫힘');
    } else results.push('· 고칠 수 없는 업무라 링크 붙이기는 건너뜀');

    await check('탭 — 논의 (되돌아오기)', () => $('dtabs').querySelector('[data-p="log"]').click(),
      {until: () => shown($('p-log'))});
    await 눌러본다('상태 배지 열기', 'statchip');
    await 눌러본다('상태 배지 다시 눌러 닫기', 'statchip');
    await 눌러본다('담당자 드롭다운', 'dassignee');
    await 눌러본다('담당팀 드롭다운', 'ddept');
    await 눌러본다('시작일 칸', 'dstart');
    await 눌러본다('논의 입력칸', 'dbody');
    await 눌러본다('대체 체크박스', 'dsuper');
    await 눌러본다('대체 체크박스 해제', 'dsuper');
    await 눌러본다('논의 취소 버튼', 'dcancelnew');

    const pen = document.querySelector('#dlog .editline');
    if (pen) {
      await 누른다('논의 수정 열기', pen);
      const box = document.querySelector('#dlog textarea.editbox');
      잰다(box, ' 편집창이 열림', '편집창이 열리지 않음');
      if (box) {
        await 누른다('편집창 안 클릭', box);
        await 누른다('편집 취소', document.querySelector('#dlog [data-cancel-edit]'));
      }
    } else results.push('· 고칠 수 있는 논의가 없어 수정은 건너뜀');

    $('dtabs').querySelector('[data-p="rel"]').click();
    await 될때까지('연결 탭으로', () => shown($('p-rel')));
    const rb = document.querySelector('#drel .rb');
    if (rb) {
      await 누른다('연결된 업무 항목', rb);
      // '이동' 은 보드에만 뜻이 있다 — 달력에는 스크롤해서 갈 자리가 없다
      const acts = [...rb.nextElementSibling.querySelectorAll('[data-act]')].map(b => b.dataset.act);
      const want = isBoard ? 'open,move' : 'open';
      잰다(acts.join(',') === want, ` 연결 메뉴가 화면에 맞음 (${acts.join(',') || '없음'})`,
        `연결 메뉴가 ${where} 에 맞지 않음`);
      await 누른다('연결 메뉴 다시 눌러 닫기', rb);
    } else results.push('· 이 업무에는 연결된 업무가 없어 건너뜀');

    // 선행 고르기 — fixed 요소라 offsetParent 가 null 이다. 그려진 크기로 판정한다.
    if ($('preedit')) {
      /* **`fixed` 는 `shown` 으로 못 본다** — `offsetParent` 가 null 이라
         늘 거짓이다(바로 위 주석이 그렇게 적어 두었는데 `until` 에는 그걸
         안 썼다). 「못 쟀음」 이 그것을 잡았다 — ✗ 로 새지 않고 「이 판에서
         답을 못 얻었다」 로 나왔다. 그려진 크기로 본다. */
      await 누른다('선행 고르기 열기', $('preedit'),
        {until: () => painted($('prepick'))});
      잰다(painted($('prepick')), ' 선행 고르기 판이 보임', '선행 고르기 판이 보이지 않음');
      await 누른다('선행 고르기 닫기', document.querySelector('#prepick [data-close]'),
        {until: () => !painted($('prepick'))});
    }

    // 진단 패널 — 하단 고정이므로 드로어를 밀어내거나 가리면 안 된다
    {
      잰다(painted($('diag')), ' 진단 패널이 하단에 그려짐', '진단 패널이 보이지 않음');
      /* **다시 그려진 것을 보고 간다** — 900ms 를 어림하던 자리다.
         판정 글자는 다시 그려도 같은 말이라 「달라졌나」 로는 못 본다.
         그래서 **누르기 전에 비우고 다시 채워지는 것을 본다** — 채우는
         곳은 `renderDiag` 하나다. 안 채워지면 「못 쟀음」 이고, 그때는
         판정이 안 왔다는 뜻이라 ✗ 로 셀 일이 아니다. */
      await check('진단 다시 분석', () => { $('dgTtl').textContent = ''; $('dgR').click(); },
        {until: () => $('dgTtl').textContent.trim()});
      /* **여기는 ✗ 가 아니다.** 바로 위 주석이 「안 채워지면 못 쟀음이고
         ✗ 로 셀 일이 아니다」 라고 적어 두었는데 코드가 ✗ 를 찍고 있었다 —
         파일이 자기와 어긋난 자리다(검토가 짚었다). 판정이 안 오면 위의
         `check` 가 이미 「못 쟀음」 으로 냈다. */
      const 판정 = $('dgTtl').textContent.trim();
      results.push(판정 ? `✓ 다시 분석 뒤 판정 유지 (${판정})`
                       : '? 다시 분석 뒤 판정 — 못 쟀음 (판정이 안 왔다)');
    }

    // 반대편도 확인 — 규칙이 과하게 걸려 정작 닫혀야 할 때 안 닫히면 안 된다.
    // 진짜 빈 점을 찾아야 한다. 고스트 바도 바이므로, 눌러도 닫히지 않는 게 정상이다.
    const emptySpot = () => {
      // 목록 — 제목 줄 오른쪽의 빈 자리. **행 밖이고** 패널도 아닌 곳이다
      // (행은 어디를 눌러도 열린다 — 4-14).
      if (isList) {
        const h = tlist.querySelector('h1');
        if (!h) return null;
        const r = h.getBoundingClientRect();
        const x = Math.round(Math.min(window.innerWidth - 24, r.right + 180));
        const y = Math.round(r.top + r.height / 2);
        const el = document.elementFromPoint(x, y);
        // 행 밖이어야 한다 — 행은 이제 어디를 눌러도 열린다 (4-14)
        if (el && !el.closest('#drawer') && !el.closest('.trow.lrow')
            && !el.closest('header,.toolbar,.sidenav')) return {x, y};
        return null;
      }
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
      잰다(closed, ' 빈 영역 클릭으로는 닫힌다', '빈 영역 클릭으로 닫히지 않음');
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
      await 될때까지("드래그 시험용 드로어 열기", () => 열렸다());
      const 열림 = dw.classList.contains("open");
      잰다(열림, " 드래그 시험을 위한 드로어 열기",
        "드래그 시험 전에 드로어를 열지 못함 — 아래 셋은 아무것도 재지 못한다");
      if (열림) {

        /* **각 항목은 앞 항목에 기대지 않는다.** 앞이 실패해 드로어가 닫히면
           뒤엣것은 `if (열려 있으면)` 에 걸려 **말없이 안 돌고**, 그러면
           "무엇이 고장인지" 가 아니라 "무엇을 쟀는지" 가 사라진다.
           고치기 전 코드로 되돌려 봤을 때 실제로 그랬다 — 본문 항목이
           빨개지자 핸들 항목이 아예 목록에 없었다. */
        const 열어둔다 = async 라벨 => {
          if (dw.classList.contains("open")) return true;
          openers()[0].click();
          await 될때까지("다시 열기: " + 라벨, () => 열렸다());
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
          // **되돌아온 것을 보고 간다** — 다음 항목이 쓰는 여백 좌표가
          // 이 폭에 달려 있다 (250ms 를 어림하던 자리)
          await 될때까지("드로어 폭 되돌리기", () => {
            const w = getComputedStyle(document.documentElement).getPropertyValue("--dw").trim();
            return w === (원래폭.trim() || "440px");
          }, 1500);
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
          // 안 닫히는 것이 고장이므로 상한까지 보고 그대로 답한다
          await 잠깐본다(() => !dw.classList.contains("open"));
          const 닫힘 = !dw.classList.contains("open");
          잰다(닫힘, " 여백을 눌렀다 떼면 닫힌다 (드래그 고침이 과하지 않다)", "드래그 고침이 과해서 여백 클릭으로도 안 닫힘");
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
          /* **여기는 기다릴 상태가 없다.** 우클릭은 화면을 안 바꾼다 —
             바뀌는 것은 스크립트 안의 기록뿐이라 밖에서 볼 수가 없다.
             한 틱만 넘겨 이벤트 순서를 지킨다(어림이 아니라 최소값). */
          await sleep(0);
          // 키보드 클릭 — pointerdown 이 없다
          const 저기 = emptySpot() || {x, y};
          const 밖 = document.elementFromPoint(저기.x, 저기.y);
          밖.dispatchEvent(new MouseEvent("click",
            {bubbles: true, cancelable: true, clientX: 저기.x, clientY: 저기.y, detail: 0, view: window}));
          // **닫히는 것을 보고 간다.** 안 닫히는 것이 고장이므로 상한까지
          // 기다렸다가 그래도 열려 있으면 그것이 답이다 (✗ 로 센다)
          await 잠깐본다(() => !dw.classList.contains("open"));
          const 닫힘2 = !dw.classList.contains("open");
          잰다(닫힘2, " 우클릭 뒤 키보드 클릭으로도 닫힌다 (옛 기록이 안 남는다)",
               "우클릭 뒤 키보드 클릭에서 옛 down/up 기록이 남아 안 닫힘");
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
      잰다(kept, ` 닫아도 보던 달이 그대로 (${calbar.dataset.month})`, '닫았더니 보던 달을 잃음');
    }

    /* 달력 탭은 드로어를 넓혀도 커지지 않아야 한다 — 한 화면에 들어와야 하므로.
       **목록에서는 이 시험이 뜻이 없다** — 패널이 행 아래에 인라인으로 들어가
       `--dw` 가 폭을 정하지 않는다(4-14). 전에는 그냥 돌려서 두 값이 같게
       나왔고 ✓ 가 붙었는데, **넓힌 적이 없으니 안 커진 것이 당연**했다.
       「못 쟀음」 이 그것을 드러냈다. */
    if (isList) {
      results.push('· 달력 칸 크기 고정 — 목록은 패널이 인라인이라 폭을 못 넓혀 건너뜀');
    } else {
    openers()[0].click();
    await 될때까지('달력 탭 시험용 열기', () => 열렸다());
    $('dtabs').querySelector('[data-p="cal"]').click();
    await 될때까지('달력 탭으로', () => document.querySelector('.cal .dcell:not(.pad)'));
    const cellW = () => { const c = document.querySelector('.cal .dcell:not(.pad)');
      return c ? Math.round(c.getBoundingClientRect().width) : 0; };
    const narrow = cellW();
    // **폭이 실제로 바뀐 것을 보고 잰다.** 250ms 를 어림하던 자리다 —
    // 전환이 남아 있을 때 재면 「커졌다」 가 되어 없는 고장이 나온다
    const 드폭 = () => Math.round(dw.getBoundingClientRect().width);
    const 좁을때폭 = 드폭();
    document.documentElement.style.setProperty('--dw', '760px');
    await 될때까지('드로어 넓히기', () => 드폭() > 좁을때폭 + 100, 2000);
    const wide = cellW();
    document.documentElement.style.setProperty('--dw', '400px');
    await 될때까지('드로어 되돌리기', () => 드폭() < 좁을때폭 + 100, 2000);
    잰다(narrow === wide, ` 달력 칸 크기 고정 (${narrow}px → ${wide}px)`,
      '드로어를 넓히면 달력이 커진다');
    }

    // ── 사이드바 (B안 · 4-0) — ≥1280px 펼침 고정이 기본, 그 아래는 접힘 + 호버.
    //    화면 이동 수단이 여기 하나뿐이라, 드로어를 연 채로도 열려야 한다.
    {
      const nav = document.getElementById('sidenav');
      const edge = document.getElementById('sideedge');
      const toggle = document.getElementById('sidetoggle');
      const wideScreen = window.innerWidth >= 1280;
      // 미끄러지는 동안을 재지 않는다. 탭이 가려져 있으면 브라우저가 그리기를
      // 멈춰 전환이 진행되지 않고, 그러면 "안 열렸다"고 잘못 말한다 — 화면이
      // 틀린 게 아니라 재는 방법이 틀린 것이다. 여기서만 전환을 끄고 끝나면 되돌린다.
      const navEase = nav.style.transition, bodyEase = document.body.style.transition;
      nav.style.transition = 'none';
      document.body.style.transition = 'none';
      const at = () => Math.round(nav.getBoundingClientRect().left);
      const pinned = () => document.body.classList.contains('sidepin');
      const wasPinned = pinned();

      // 기본 상태 — 저장값이 없으면 넓은 화면은 펼침, 좁은 화면은 접힘.
      let saved = null; try { saved = localStorage.getItem('dcb.sidepin'); } catch (e) {}
      const expectPinned = saved === '1' || (saved === null && wideScreen);
      잰다(pinned() === expectPinned,
        ` 사이드바 기본 상태가 1280px 기준과 저장값을 따른다 (pinned=${pinned()})`,
        '사이드바 기본 상태가 틀림');
      if (wideScreen) {
        const openWide = !pinned() || (at() === 0 && parseInt(getComputedStyle(document.body).paddingLeft, 10) > 100);
        잰다(openWide, ' 넓은 화면 고정 시 펼쳐지고 본문이 밀린다', '넓은 화면에서 고정이 본문을 밀지 않음');
      }

      if (wasPinned) {
        toggle.click();
        await 될때까지('사이드바 접기', () => at() < 0, 1500);
      }
      잰다(at() < 0, ` 고정을 풀면 접힌다 (left ${at()}px)`, '고정을 풀어도 접히지 않음');

      잰다(!document.querySelector('nav.tabs'), ' 상단 탭 줄이 없음', '상단 탭 줄이 남아 있음');

      // 그룹 제목은 링크이고 활성 표시는 하위에만 (3장)
      const groups = [...nav.querySelectorAll('a.g')];
      const groupOk = groups.length >= 3 && groups.every(g => g.getAttribute('href')
        && !g.hasAttribute('aria-current'));
      잰다(groupOk, ` 그룹 제목 ${groups.length}개가 링크이고 활성 표시가 없다`, '그룹 제목이 링크가 아니거나 활성 표시가 붙음');
      const onGroups = [...nav.querySelectorAll('.g[aria-current], .g.on')];
      잰다(onGroups.length === 0, ' 선택 표시는 하위에만', '그룹에 선택 표시가 있음');

      // 가장자리 호버 — 잠깐 들춰 본다. 본문은 밀리지 않는다.
      await check('사이드바 — 가장자리 호버', async () => {
        edge.dispatchEvent(new MouseEvent('mouseenter', {bubbles: false}));
      }, {until: () => at() === 0});
      const peeked = at() === 0 && getComputedStyle(document.body).paddingLeft === '0px';
      잰다(peeked, ' 가장자리 호버로 잠깐 열리고 본문은 그대로', '가장자리 호버가 동작하지 않음');
      nav.dispatchEvent(new MouseEvent('mouseleave', {bubbles: false}));
      await 될때까지('가장자리에서 손 떼기', () => at() < 0, 1500);

      // 토글 — 고정한다. 본문이 밀리는 것은 ≥1280 에서만이다 (그 아래는 CSS 가 무시).
      await 누른다('사이드바 — 토글로 고정', toggle,
        {until: () => pinned() && at() === 0, mayScroll: true});
      const pad = parseInt(getComputedStyle(document.body).paddingLeft, 10);
      const pin = pinned() && (wideScreen ? (at() === 0 && pad > 100) : pad === 0);
      잰다(pin, (wideScreen ? ' 토글로 고정하면 본문이 밀린다' : ' 좁은 화면에서는 고정해도 본문이 밀리지 않는다'),
           '토글 고정이 1280px 기준과 다르게 동작함');
      await 누른다('사이드바 — 토글로 접기', toggle,
        {until: () => !pinned(), mayScroll: true});
      if (wasPinned) {
        toggle.click();
        await 될때까지('사이드바 되돌리기', () => pinned(), 1500);
      }
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
      잰다(lined.length === 0, ` 가로 격자선 없음 (${lined.length}줄)`, '행에 가로선이 남아 있음');
      const vert = [...sheet.querySelectorAll('.gridlines i')].length;
      잰다(vert > 0, ` 세로 격자선은 남아 있음 (${vert}개)`, '세로 격자선이 사라짐');

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
      /* **여기는 기다릴 상태가 없다.** 클래스를 붙인 뒤 「계산된 배경」 을
         읽는 것이라, 바뀌기를 기다릴 요소가 없고 브라우저가 다시 그릴
         틈만 주면 된다. `getComputedStyle` 을 한 번 읽어 레이아웃을
         강제하고(어림이 아니라 확정), 한 틱만 넘긴다. */
      const 한틱 = async () => { void document.body.offsetHeight; await sleep(0); };
      const 켜고잰다 = async (el, cls) => {
        el.classList.add(cls);
        await 한틱();
        const ok = 불투명(el);
        el.classList.remove(cls);
        await 한틱();
        return ok;
      };
      const main = [...sheet.querySelectorAll('.row.main .lc, .row.sub .lc')].filter(shown)[0];
      const team = [...sheet.querySelectorAll('.row.team .lc')].filter(shown)[0];
      if (main && team) {
        const 잰값 = {
          평소: 불투명(main),
          호버: await 켜고잰다(main, 'is-hover'),
          부서호버: await 켜고잰다(team, 'is-hover'),
          연결: await 켜고잰다(main.closest('.row'), 'hl') && true,
        };
        // `.hl`·`.anchorrow` 는 줄에 붙으므로 줄에 붙였다 뗀 뒤 칸을 다시 잰다
        const row = main.closest('.row');
        row.classList.add('hl'); await 한틱();
        잰값.연결 = 불투명(main);
        row.classList.remove('hl');
        row.classList.add('anchorrow'); await 한틱();
        잰값.선택 = 불투명(main);
        row.classList.remove('anchorrow'); await 한틱();

        const ok = Object.values(잰값).every(Boolean);
        잰다(ok, ' 왼쪽 라벨 열이 불투명 (' + Object.entries(잰값).map(([k, v]) => `${k} ${v ? 'O' : 'X'}`).join(' · ') + ')',
             '왼쪽 라벨 열 배경이 반투명 — 뒤의 바가 비친다');
      }
    } else if (isList) {
      // 목록 (4-14) — 완료는 기본 접힘, 「완료 N건 보기」 로 편다
      const done = document.querySelector('details.ldone');
      if (done) {
        /* **언제나 ✓ 이던 줄이다.** 「자리가 있다」 만 찍고 열렸는지
           닫혔는지는 안 봤다 — 항목 수에는 들어가면서 아무것도 안 재는
           줄은 만점을 만든다(봐둘것 AJ-d). 4-14 는 「완료는 기본 접힘」
           이라고 정했으므로 그것을 잰다: **그 안에 펼친 업무가 있을
           때만** 열려 있어야 한다(`?task=` 로 들어온 경우). */
        const 안에펼침 = !!done.querySelector('.lslot:not([hidden])');
        잰다(done.open === 안에펼침,
          ` 완료는 기본 접힘 (open=${done.open} · 안에 펼친 업무 ${안에펼침 ? '있음' : '없음'})`,
          '완료 접힘이 기본 상태와 다름');
        // 접힘을 펴도 드로어·스크롤이 그대로다
        await check('완료 접힘 펴기', () => { done.open = true; }, {mayScroll: false});
        done.open = false;
      } else results.push('· 완료 업무가 없어 접힘 자리는 건너뜀');
      // **행의 빈 곳을 눌러도 열린다** (4-14) — 예외는 안 여는 자리뿐이다
      {
        const row = [...document.querySelectorAll('.trow.lrow')].filter(shown)[0];
        const meta = row && row.querySelector('.metaline');
        if (meta) {
          if (dw.classList.contains('open')) {
            Drawer.close();
            await 될때까지('행 접기(메타 시험 전)', () => !dw.classList.contains('open'), 1500);
          }
          meta.click();                     // 이름도 캐럿도 아닌 자리
          await 잠깐본다(() => 열렸다(), 2000);
          const opened = dw.classList.contains('open');
          잰다(opened, ' 행의 빈 곳(메타)을 눌러도 열림', '행의 빈 곳을 눌러도 안 열린다');
        }
        /* 상태 칸 — **바꿀 수 있을 때만** 안 여는 자리다 (4-14).
           배지 안쪽과 칸의 가장자리가 같은 자리여야 한다: 몇 px 차이로
           열림과 메뉴가 갈리면 같은 곳을 눌렀는데 다른 일이 난다.

           **못 바꾸는 사람의 그 칸은 행의 다른 곳과 같아서 행을 연다.**
           예외는 「누르면 뭔가 되는 것」 이지 「누를 수 없는 사람에게도
           예외」 가 아니다. 전에는 여기가 권한과 무관하게 「안 열려야
           한다」 고 적혀 있었는데, 그러면 **관리자로 돌 때만 우연히
           통과하고** 부서 리더 화면에서는 맞는 동작이 ✗ 로 나온다. */
        const 칸있는행 = 고를수 => [...document.querySelectorAll('.trow.lrow')]
          .filter(r => shown(r) && !r.classList.contains('open'))
          .find(r => { const c = r.querySelector('.cell.st');
                       return c && c.classList.contains('pick') === 고를수; });
        const menu = $('statmenu');
        for (const 고를수있나 of [true, false]) {
          const row = 칸있는행(고를수있나);
          const stcell = row && row.querySelector('.cell.st');
          if (!stcell) {
            results.push(`· 이 계정에는 ${고를수있나 ? '바꿀 수 있는' : '못 바꾸는'}`
              + ' 상태 칸이 없어 건너뜀');
            continue;
          }
          for (const [어디, el] of [['배지', stcell.querySelector('.stbadge') || stcell],
                                   ['칸의 가장자리', stcell]]) {
            const before = new URLSearchParams(location.search).get('task');
            el.click();
            /* **둘 다 답이 될 수 있는 자리다** — 바꿀 수 있으면 안 열리는
               것이 맞고, 못 바꾸면 열리는 것이 맞다. 그래서 「열림」 을
               상한까지 보고 그대로 답한다(못 쟀음이 아니다) */
            await 잠깐본다(() =>
              new URLSearchParams(location.search).get('task') !== before, 1200);
            const 열렸나 = new URLSearchParams(location.search).get('task') !== before;
            // 바꿀 수 있으면 안 열려야 하고, 못 바꾸면 행처럼 열려야 한다
            const 맞나열림 = 고를수있나 ? !열렸나 : 열렸나;
            잰다(맞나열림, ` 상태 ${어디} → 행 ${열렸나 ? '열림' : '안 열림'}` + ` (바꿀 수 ${고를수있나 ? '있음' : '없음'})`,
                 `상태 ${어디}의 열림이 권한과 어긋남`);
            const 떴나 = !!(menu && menu.classList.contains('on'));
            const 맞나 = 고를수있나 ? 떴나 : !떴나;
            잰다(맞나, ` 상태 ${어디} → 메뉴 ${떴나 ? '뜸' : '안 뜸'}` + ` (바꿀 수 ${고를수있나 ? '있음' : '없음'})`,
                 `상태 ${어디}의 메뉴가 권한과 어긋남`);
            /* **닫힌 것을 보고 다음으로 간다.** 250ms 를 기다리기만 했더니
               일곱 판 중 한 번, 아직 열려 있는 채로 다음 클릭이 들어가
               `statMenu` 가 **토글로 닫아** 「메뉴가 안 떴다」 가 됐다 —
               화면이 아니라 검사가 흔들린 것이다(4-14 의 「배지를 다시
               누르면 목록만 닫힌다」 가 제대로 동작한 결과였다). */
            if (떴나) {
              document.body.click();
              await 될때까지('상태 메뉴 닫기', () => !menu.classList.contains('on'), 1500);
            }
            if (열렸나) {
              Drawer.close();
              await 될때까지('행 접기', () => !dw.classList.contains('open'), 1500);
            }
          }
        }
      }
      // 같은 행을 다시 누르면 닫힌다 (토글)
      const first = openers()[0];
      if (first && !dw.classList.contains('open')) {
        first.click();
        await 될때까지('토글 시험용 열기', () => 열렸다());
      }
      if (first && dw.classList.contains('open')) {
        const cur = new URLSearchParams(location.search).get('task');
        document.querySelector(`.trow.lrow[data-run="${cur}"] .nm`)?.click();
        // 안 닫히는 것이 고장이므로 상한까지 보고 그대로 답한다
        await 잠깐본다(() => !dw.classList.contains('open'));
        const closed = !dw.classList.contains('open');
        잰다(closed, ' 같은 행을 다시 누르면 닫힘', '같은 행 토글이 닫지 않음');
        const urlCleared = !new URLSearchParams(location.search).get('task');
        잰다(urlCleared, ' 닫으면 ?task= 가 주소에서 빠짐', '닫아도 ?task= 가 남음');
      }
    } else {
      // 달력은 **마감일에 점 하나**다. 기간 띠가 아니다 (CLAUDE.md 4-13).
      const dots = document.querySelectorAll('.cal-dot').length;
      잰다(dots > 0, ` 마감일에 점이 그려짐 (${dots}개)`, '달력에 점이 없음');
      /* 날짜 없는 업무를 조용히 빼지 않는다 (4-13) — **있을 때만** 본다.
         **언제나 ✓ 이던 줄이다.** 있든 없든 ✓ 를 찍어서, 자리가 사라져도
         아무 말이 없었다(봐둘것 AJ-d). 이제 있으면 **건수가 적혀 있는지**
         를 재고, 없으면 그건 이 달의 사정이라 건너뜀으로 센다 — 없는 것을
         ✓ 로 세면 「전부 쟀다」 가 부풀어 오른다. */
      const undated = document.querySelector('.calundated');
      if (undated) {
        const 머리 = (undated.querySelector('summary') || {}).textContent || '';
        잰다(/\d/.test(머리), ` 날짜 없는 업무 자리에 건수가 있음 (${머리.trim()})`,
          '날짜 없는 업무 자리에 건수가 없다');
      } else results.push('· 이번 달엔 날짜 없는 업무가 없어 건너뜀');

      // 점에 마우스를 올리면 그 업무의 기간이 비친다 (4-13).
      // **마감일에 점 하나** 는 그대로다 — 한 번에 하나만, 떼면 사라진다.
      const withSpan = [...document.querySelectorAll('.cal-dot[data-start]')].filter(shown);
      if (withSpan.length && matchMedia('(min-width: 821px)').matches) {
        const dot = withSpan.find(d => d.dataset.start !== d.dataset.end) || withSpan[0];
        dot.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
        // **비치는 것을 보고 간다.** 안 비치면 그것이 답이라 잠깐본다
        await 잠깐본다(() => document.querySelectorAll('.cal-cell.inspan').length > 0, 1200);
        const 칠해진 = [...document.querySelectorAll('.cal-cell.inspan')];
        const 맞는가 = 칠해진.length > 0 && 칠해진.every(td =>
          dot.dataset.start <= td.dataset.date && td.dataset.date <= dot.dataset.end);
        잰다(맞는가, ` 점에 올리면 기간이 비침 (${칠해진.length}칸)`, '기간 비침이 동작하지 않음');

        // 오늘 칸의 파란 테두리가 비침에 덮이지 않는다
        const today = document.querySelector('.cal-cell.today');
        if (today) {
          const 남음 = getComputedStyle(today).boxShadow !== 'none';
          잰다(남음, ' 오늘 칸 테두리가 비침 위에 남음', '오늘 칸 테두리가 덮임');
        }

        dot.dispatchEvent(new MouseEvent('mouseout', {bubbles: true, relatedTarget: document.body}));
        await 잠깐본다(() => document.querySelectorAll('.cal-cell.inspan').length === 0, 1200);
        const 지워짐 = document.querySelectorAll('.cal-cell.inspan').length === 0;
        잰다(지워짐, ' 손을 떼면 사라짐', '비침이 남아 있음');
      } else results.push('· 기간을 가진 점이 없거나 좁은 화면이라 건너뜀');
    }

    /* **안 잰 것을 안 잰 것으로 낸다.** `·` 로 시작하는 줄은 건너뛴
       항목이고 errors 를 늘리지 않는다 — 그래서 「92/92」 가 「전부 쟀고
       전부 통과」 로 읽히는데, 실은 「빨간 것이 없다」 일 뿐이다.
       실제로 관리자 계정으로만 돌리면 「못 바꾸는 상태 칸」 두 쌍이 한
       번도 안 재지는데 점수는 만점이었다 (11-3 의 「센 것이 0이면 성공이
       아니라 실패」 와 같은 자리 — 검토가 짚었다). */
    완주 = true;
  } catch (e) {
    잰다(false, ` 점검이 끝까지 돌지 못함 (${(e && e.message) || e})`,
      '점검이 중간에 죽었다: ' + ((e && e.message) || e));
  }
  // 첫 줄은 「돌린 화면」 표시라 뺀다. 그리고 **항목 수는 이 줄을 붙이기
  // 전 값**이다 — 요약이 항목 수를 늘리면 판마다 수가 달라 보인다
  const 잰것 = results.length;
  const 건너뜀 = results.slice(1).filter(r => String(r).startsWith('·')).length;
  /* **어느 계정으로 다시 돌아야 하는지까지 말한다.** 「N개 건너뜀」 만
     내면 다음 사람은 그것을 보고도 무엇을 해야 할지 모른다 — 관리자로
     돌면 모든 행이 「바꿀 수 있음」 이라 못 바꾸는 쪽이 안 재진다. */
  if (건너뜀) {
    /* **어림하지 않는다 — 화면이 역할을 글자로 말한다.** 사이드바
       아래의 사용자 카드가 `ROLE_LABELS` 로 「총무팀(관리자)」·「부서
       리더」 를 찍는다(`retreat_base.html`). 처음에는 「지금 고칠 수
       있나」 로 어림했는데, 부서 리더가 자기 부서 업무를 첫 자리에서
       열면 참이 되어 **자기 계정을 다시 권한다**(검토가 짚었다).
       카드가 없으면 그때만 어림으로 물러선다. */
    const 역할 = (document.querySelector('.sidefoot .who small') || {}).textContent || '';
    const 관리자 = 역할.includes('관리자') || (!역할 &&
      !document.querySelector('#statchip[disabled]'));
    results.push(`· 이 계정에서 안 재진 항목 ${건너뜀}개 — `
      + (관리자 ? '**부서 리더** 계정으로 한 번 더 돌려 보세요'
               : '**관리자** 계정으로 한 번 더 돌려 보세요')
      + ' (한 계정으로는 권한 두 쪽을 다 못 잽니다)');
  }
  /* **표에 찍히기 전에 붙인다.** 전에는 `console.table` 뒤에 붙여서
     돌려준 값에만 있고 콘솔 표에는 안 나왔다 — 콘솔만 보는 사람에게는
     못 쟀음이 **없는 것과 같았다**. 건너뜀 줄은 위에서 이미 붙였다. */
  if (못쟀음.length) results.push(`? 못 쟀음 ${못쟀음.length}개 — 화면이 틀린 것이`
    + ' 아니라 이 판에서 답을 못 얻은 것입니다 (주변은 그대로인데'
    + ' 기다린 상태가 안 나타남 — 그 줄이 무엇을 기다리는지 보세요)');
  console.table(results);
  return {화면: where, 통과: errors.length === 0 && 완주, 완주, 실패: errors,
          항목수: 잰것, 건너뜀, 못쟀음, 항목: results};
};

/* ── 자가시험 — 고장을 심어서 검사를 검사한다 ───────────────────────
   「못 쟀음」 이 진짜 회귀를 숨기고 있던 것을 한 번 **손으로** 심어서
   잡았다. 그런데 그 심기를 남기지 않으면 **다음 입구는 못 잡는다** —
   검사가 볼 것을 실제로 보는지는 검사 자신이 증명해야 한다
   (11-3 「막는 코드에는 막히는 쪽 시험이 함께 있다」 의 셋째 축).

   갈래마다 고장을 하나씩 심었다 걷어내며 그것이 **✗ 로 나오는지** 잰다.
   ✗ 가 아니라 「못 쟀음」 이나 통과로 나오면 **자가시험이 실패**한다 —
   그 자리가 검사가 새는 입구다 (봐둘것 AH-b).

   **평소 점검과 따로 돈다.** 갈래 수만큼 점검을 다시 돌리므로 평소에
   켜 두면 그만큼 느려진다. 켜는 법 — 이 파일을 붙여넣기 **전에**

       window.__자가시험 = 1;

   **언제 돌리나 — 점검 스크립트를 고친 판에서는 반드시** (11-3 2단계).

   심을 수 없는 갈래가 셋 있고, ✗ 가 아닌 것이 그쪽의 정답이다.
     · 건너뜀(죽은·없는 요소)  — 심으면 `·` 가 늘 뿐이다. 그게 맞다
     · 못 쟀음(주변은 멀쩡한데 기다린 것이 안 나타남) — ✗ 가 아닌 것이 정의다.
       다만 **주변이 무너진 채로 못 쟀을 때 ✗ 인지**는 ① 이 함께 잰다
     · 치명(드로어가 안 열림) — 항목이 아예 안 만들어져 ✗ 가 나올 자리가 없다 */
const 스타일 = css => {
  const s = document.createElement('style');
  s.textContent = css;
  document.head.appendChild(s);
  return () => s.remove();
};
/* **캡처에서 막는다.** 앱은 요소의 `onclick` 이나 window 의 버블 핸들러로
   듣는데, document 캡처에서 전파를 끊으면 둘 다 안 닿는다 — 앱 코드를
   건드리지 않고 「눌러도 아무 일이 없다」 를 만드는 가장 얇은 길이다. */
const 캡처막기 = (골라, 무엇 = 'click') => {
  const f = e => { if (e.target instanceof Element && 골라(e.target)) e.stopPropagation(); };
  document.addEventListener(무엇, f, true);
  return () => document.removeEventListener(무엇, f, true);
};

const 고장들 = [
  {갈래: '① 주변 붕괴', 고장: '드로어 안을 누르면 패널이 닫힌다',
   나와야: '드로어가 닫힘',
   심는다: () => {
     const f = e => {
       if (e.target instanceof Element && e.target.closest('#drawer')) Drawer.close();
     };
     document.addEventListener('click', f, true);
     return () => document.removeEventListener('click', f, true);
   }},
  {갈래: '② 조작이 안 먹음', 고장: '제목을 눌러도 편집칸이 안 열린다',
   나와야: '제목 입력칸이 열리지 않음',
   못심음: 항목 => 항목.some(r => String(r).includes('제목 편집은 건너뜀')),
   심는다: () => 캡처막기(el => el.closest('#dtitletext'))},
  {갈래: '③ 화면 구조', 고장: '첨부파일 탭이 맨 끝이 아니다',
   나와야: '첨부파일 탭이 맨 끝이 아님',
   심는다: () => {
     const bar = document.getElementById('dtabs');
     const 끝 = [...bar.querySelectorAll('button')].pop();
     bar.insertBefore(끝, bar.firstChild);
     return () => bar.appendChild(끝);
   }},
  /* **여기는 계정을 보고 반대로 심는다.** 고칠 수 있는 계정에서는 숨기고,
     못 고치는 계정에서는 **보이게** 한다 — 어느 쪽이든 「권한과 어긋남」 이다.
     한 방향으로만 심으면 부서 리더에게는 이미 숨겨져 있어 아무 일도 안
     일어나고, 그 갈래를 그 계정에서 **한 번도 못 재게** 된다. */
  {갈래: '④ 권한과 어긋남', 고장: '논의 입력칸이 권한과 반대로 보인다',
   나와야: '논의 입력칸이 권한과 어긋남',
   심는다: 항목 => 스타일(항목.some(r => String(r).includes('고칠 수 없음'))
     ? '#daddlog{display:block!important}'
     : '#daddlog{display:none!important}')},
  {갈래: '⑤ 닫혀야 할 때 안 닫힘', 고장: '여백 클릭이 드로어까지 닿지 않는다',
   나와야: '빈 영역 클릭으로 닫히지 않음',
   못심음: 항목 => 항목.some(r => String(r).includes('빈 칸이 없어')),
   // 업무를 여는 자리와 머리·사이드바는 살려 둔다 — 그것까지 막으면
   // 드로어가 아예 안 열려 **치명**이 되고, 심은 고장을 잴 수가 없다
   심는다: () => 캡처막기(el => !el.closest(
     '#drawer,#statmenu,.bar[data-run],.cal-dot,.trow,header,.toolbar,.calbar,.sidenav'))},
  /* **넉넉히 넘긴다.** 44px 로 심었더니 **목록에서만 통과로 지나갔다** —
     그 화면은 패널이 행 아래 인라인이라 탭 바가 훨씬 넓어서 안 넘쳤다.
     고장이 화면에 따라 약하면 그 갈래를 거기서 못 잰다(자가시험이
     2026-09-09 에 그것을 잡았다). 어느 폭에서도 넘칠 값으로 올린다. */
  {갈래: '⑥ 계산된 스타일·자리', 고장: '탭이 드로어 폭을 넘쳐 첨부파일이 잘린다',
   나와야: '탭이 넘쳐 첨부파일이 잘림',
   심는다: () => 스타일(
     '#dtabs button{padding-left:400px!important;padding-right:400px!important}')},

  /* ── 건너뛰는 길도 심어 본다 ─────────────────────────────────────
     **여기는 ✗ 가 아닌 것이 정답이다.** 죽어 있거나 없는 요소를 누르면
     `살아있나` 가 걸러 **건너뜀**으로 세야 한다 — 심었더니 ✗ 가 나오면
     그것이 고장이다. 「심어 본 적은 없습니다」 로 남겨 두던 자리다
     (봐둘것 AJ-a). `나와야` 대신 `건너뜀나와야` 를 쓴다. */
  {갈래: '⑦ 죽은·없는 요소는 건너뜀', 고장: '담당자 드롭다운이 화면에서 사라진다',
   건너뜀나와야: '담당자 드롭다운',
   못심음: 항목 => 항목.some(r => String(r).includes('담당자 드롭다운 — 이 계정에는')),
   심는다: () => 스타일('#dassignee{display:none!important}')},

  /* ── 화면에만 있는 갈래 ──────────────────────────────────────────
     **갈래는 화면을 가로질러 같은 길을 지나지만, 그 화면에만 있는 판정
     줄은 다른 화면에서 한 번도 안 지납니다**(봐둘것 AJ-c). 목록의 상태
     칸과 달력의 비침이 그것이라, 그 화면에서만 심는다. */
  {갈래: '⑧ 목록 — 상태 칸', 고장: '상태 칸을 눌러도 아무 일이 없다',
   화면: '목록', 나와야: '의 메뉴가 권한과 어긋남',
   못심음: 항목 => !항목.some(r => String(r).includes('상태 배지 →')),
   심는다: () => 캡처막기(el => el.closest('.cell.st'))},
  {갈래: '⑨ 목록 — 완료 접힘', 고장: '완료가 기본으로 펼쳐져 있다',
   화면: '목록', 나와야: '완료 접힘이 기본 상태와 다름',
   못심음: 항목 => 항목.some(r => String(r).includes('완료 업무가 없어')),
   심는다: () => {
     const done = document.querySelector('details.ldone');
     const 원래 = done.open;
     done.open = !done.open;
     return () => { done.open = 원래; };
   }},
  {갈래: '⑩ 달력 — 기간 비침', 고장: '점에 올려도 기간이 안 비친다',
   화면: '달력', 나와야: '기간 비침이 동작하지 않음',
   못심음: 항목 => 항목.some(r => String(r).includes('기간을 가진 점이 없거나')),
   심는다: () => 캡처막기(el => el.closest('.cal-dot'), 'mouseover')},
  {갈래: '⑪ 달력 — 날짜 없는 업무', 고장: '건수가 사라진다',
   화면: '달력', 나와야: '날짜 없는 업무 자리에 건수가 없다',
   못심음: 항목 => 항목.some(r => String(r).includes('날짜 없는 업무가 없어')),
   심는다: () => {
     const s = document.querySelector('.calundated summary');
     const 원래 = s.textContent;
     s.textContent = '날짜 없는 업무';
     return () => { s.textContent = 원래; };
   }},

  /* ── 점검이 통째로 죽는 것 ───────────────────────────────────────
     같은 이름의 지역 변수 하나가 판정 줄을 가려 점검이 한복판에서
     죽었고, **그때 알아본 것은 사람이지 출력이 아니었습니다**(AJ-b).
     이제 출력이 스스로 말하므로 그것도 심어서 잰다 — 한복판에서
     예외를 던지고 `완주: false` 가 나오는지 본다. */
  {갈래: '⑫ 점검이 중간에 죽음', 고장: '한복판에서 예외를 던진다',
   나와야: '점검이 중간에 죽었다', 완주못함: true,
   심는다: () => {
     const 원래 = document.querySelector.bind(document);
     document.querySelector = 무늬 => {
       if (String(무늬).includes('#drel .rb')) throw new Error('심은 고장');
       return 원래(무늬);
     };
     return () => { document.querySelector = 원래; };
   }},
];

const 자가시험 = async () => {
  /* **재는 것이 있는지 먼저 본다.** 이미 빨간 판에서 심으면, 나온 ✗ 가
     내가 심은 것인지 원래 있던 것인지 갈 수 없다 (점검 자신의 ③ 과 같은 자리). */
  const 깨끗 = await 점검();
  if (깨끗.치명) return {자가시험: false, 치명: 깨끗.치명};
  if (깨끗.실패.length) return {자가시험: false, 실패: 깨끗.실패,
    까닭: '심기 전부터 ✗ 가 있습니다 — 그것을 먼저 고치세요'};

  const 표 = [];
  let 놓친갈래 = 0, 못심은갈래 = 0;
  for (const g of 고장들) {
    /* **화면에만 있는 갈래는 그 화면에서만 심는다.** 「안 해 봤다」 가
       아니라 「이 화면에 그 자리가 없다」 이고, 그 화면에서 돌리면
       재진다 — 어느 쪽인지 나온것에 적는다. */
    const 못심는까닭 = g.화면 && g.화면 !== 깨끗.화면
      ? `· 못 심음 — ${g.화면} 화면에만 있는 자리다 (${g.화면}에서 돌리면 재진다)`
      : g.못심음 && g.못심음(깨끗.항목)
      ? '· 못 심음 — 이 계정·화면에는 그 자리가 없다'
      : '';
    if (못심는까닭) {
      못심은갈래++;
      표.push({갈래: g.갈래, 심은고장: g.고장, 나온것: 못심는까닭});
      continue;
    }
    const 걷어낸다 = g.심는다(깨끗.항목);
    let 판;
    try { 판 = await 점검(); } finally { 걷어낸다(); }
    const 실패 = (판.실패 || []).map(String);
    /* **건너뜀 갈래는 ✗ 가 아닌 것이 정답이다.** 그 `·` 줄이 나오고
       ✗ 가 하나도 안 늘어야 잡은 것이다 — 심었는데 ✗ 가 나면 그쪽이
       고장이다. */
    const 잡혔나 = g.건너뜀나와야
      ? (판.항목 || []).some(r => String(r).startsWith('·')
          && String(r).includes(g.건너뜀나와야)) && !실패.length
      : 실패.some(x => x.includes(g.나와야)) && (!g.완주못함 || 판.완주 === false);
    if (!잡혔나) 놓친갈래++;
    표.push({갈래: g.갈래, 심은고장: g.고장,
             나온것: 잡혔나 ? (g.건너뜀나와야 ? '· 건너뜀 — 잡음' : '✗ — 잡음')
               : (판.못쟀음 || []).length ? '? 못 쟀음으로 샘 — 검사가 새는 입구다'
               : '통과로 지나감 — 검사가 새는 입구다',
             실패수: 실패.length, 못쟀음수: (판.못쟀음 || []).length,
             완주: 판.완주});
  }
  console.table(표);
  /* **센 것이 0 이면 성공이 아니라 실패다** (11-3). 못 심은 갈래만
     늘어나면 「놓친 갈래 0」 이 되는데, 그건 다 잡았다는 뜻이 아니라
     **아무것도 안 재 봤다**는 뜻이다 — 실명 검사가 29개 중 0개를 보며
     초록을 내던 그 모양이다. */
  const 잰갈래 = 고장들.length - 못심은갈래;
  if (!잰갈래) console.warn('자가시험 — 이 계정·화면에서는 심을 수 있는 갈래가 하나도 없습니다');
  return {자가시험: 놓친갈래 === 0 && 잰갈래 > 0, 화면: 깨끗.화면, 갈래: 표,
          잰갈래, 놓친갈래, 못심은갈래,
          깨끗한판: {항목수: 깨끗.항목수, 건너뜀: 깨끗.건너뜀,
                   못쟀음: 깨끗.못쟀음.length}};
};

return window.__자가시험 ? 자가시험() : 점검();
})()
