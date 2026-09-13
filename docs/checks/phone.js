/* 휴대폰 폭 상호작용 점검 — **누르는 것이 실제로 눌리는가.**
 *
 * 쓰는 법: 브라우저를 **휴대폰 폭(820px 아래)** 으로 두고 로그인한 뒤
 * 아무 화면에서나 콘솔에 이 파일 내용을 붙여넣습니다.
 *
 * **왜 따로 만들었나 — `docs/checks/drawer.js` 를 안 넓혔습니다.**
 * 그쪽은 상세 패널의 조작을 재고 **1440×900 을 전제**합니다(바를 끌고,
 * 폭을 조절하고, 달력 칸에 마우스를 올립니다 — 좁은 화면에서는 그 자리들이
 * 아예 없거나 뜻이 다릅니다). 한 파일에 넣으면 그 항목들이 전부 「건너뜀」
 * 으로 빠져 **「N/N 통과」 가 또 뜻을 잃습니다** — 그쪽이 회차를 고르라고
 * 적어 둔 것과 같은 자리입니다. 재는 전제가 다르면 파일도 다릅니다.
 *
 * **왜 생겼나** — 2026-09-12 에 휴대폰에서 **아무 데도 못 갔습니다.**
 * 화면은 그려지는데 목록(햄버거) 단추를 눌러도 아무 일이 없었습니다.
 * 토글은 `body.sidepin` 만 붙이는데 CSS 는 1280px 아래에서 그것을 무시했고,
 * 여는 길이 **가장자리 호버뿐**이었습니다 — 손가락에는 호버가 없습니다.
 * 상단 탭 줄이 없으므로(4-0) 그때 이동 수단은 통째로 없었습니다.
 *
 * **이 고장이 아무 눈에도 안 걸렸습니다.** pytest 는 브라우저를 안 열고,
 * 검토자는 코드를 읽고, 상세 패널 점검은 넓은 화면에서만 돕니다.
 * **휴대폰 폭에서 실제로 눌러 본 자리가 없었습니다.** 이 파일이 그 자리입니다.
 *
 * 무엇을 보는가 — 사람이 실제로 막힌 순서 그대로입니다.
 *   · 로그인된 화면인가 (사이드바에 그 사람이 있는가)
 *   · 화면이 그려졌는가 (그려지기 전의 「안 눌림」 과 가르기 위해)
 *   · **메뉴 단추를 누르면 사이드바가 화면 안으로 들어오는가**
 *   · 단추의 보이는 말과 읽어 주는 이름이 같은가 (2026-09-13)
 *   · 손가락 기기에서 본문이 누를 수 있는 것으로 보이는가 — 아이폰의
 *     「바깥을 눌러 닫기」 가 그 한 줄에 걸려 있다 (2026-09-13)
 *   · 그 사이드바에서 **화면을 옮길 수 있는가**
 *   · 다시 누르면 닫히는가 · 바깥을 누르면 닫히는가
 *   · 왼쪽 가장자리 띠가 본문의 누름을 가져가지 않는가
 *
 * 보임은 속성이 아니라 **그 자리에서 실제로 누름을 받는 것이 무엇인가**로
 * 봅니다 — `el.hidden` 도 `display` 도 「덮여 있다」 를 말해 주지 않습니다
 * (10장). `document.elementFromPoint` 로 집어 봅니다.
 *
 * **정말로 화면을 옮기지는 않습니다.** 옮겨 버리면 그 순간 이 스크립트가
 * 죽어 나머지를 못 잽니다. 대신 **누름이 그 링크에 닿았는지**를 링크
 * 자신에게서 듣고, 가려는 곳은 잠깐 같은 페이지 안으로 갈아 끼웁니다.
 *
 * **돌리기 전에 화면을 손으로 헤집어 두지 마세요.** 자가시험은 갈래
 * 사이사이에 판을 고르지만, **첫 판은 그 페이지가 있는 그대로** 시작합니다 —
 * 사이드바를 손으로 열어 둔 채 돌리면 「안 심으면 초록」 이 빨갛게 나옵니다.
 * 새로 고친 뒤에 돌리는 것이 가장 깨끗합니다.
 *
 * **자가시험** — 붙여넣기 전에 `window.__자가시험 = 1;` 을 실행하면
 * 갈래마다 고장을 하나씩 심었다 걷어내며 **✗ 로 나오는지** 잽니다.
 * 심는 고장 하나는 **2026-09-12 에 실제로 났던 그 고장**입니다(토글이
 * `sidepin` 만 붙이던 옛 동작) — 고친 자리를 되돌려 심는 것이 가장
 * 정확합니다. 이 파일이나 사이드바를 고친 판에서는 반드시 돌립니다(11-3 2단계).
 */
(async () => {
const 점검 = async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const $ = id => document.getElementById(id);
  const errors = [], results = [], 못쟀음 = [];

  /* ✗ 를 찍는 길과 세는 길은 하나다 — 둘이면 손으로 맞추게 되고 실제로
     어긋난 적이 있다(drawer.js 의 그 자리). */
  const 잰다 = (ok, 라벨, 까닭) => {
    results.push((ok ? '✓' : '✗') + 라벨);
    if (!ok) errors.push(까닭 === undefined ? 라벨.trim() : 까닭);
    return ok;
  };
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

  const nav = $('sidenav'), toggle = $('sidetoggle');
  if (!nav || !toggle) return {치명: '이 화면에는 사이드바가 없습니다 (로그인한 뒤 돌리세요)'};

  /* ── 전제: 휴대폰 폭인가 ──────────────────────────────────────────
     **넓은 화면에서 돌면 전부 초록이 나오고 아무것도 안 잰 것이 된다** —
     이 고장이 정확히 넓은 화면에서는 안 났다. 그래서 폭을 항목이 아니라
     **전제**로 둔다: 아니면 돌지 않고 그렇게 말한다. */
  const 폭 = window.innerWidth;
  if (폭 > 820) return {치명: `창이 ${폭}px 입니다 — 이 점검은 휴대폰 폭(820px 아래)에서 돌립니다.`
    + ' 넓은 화면에서 돌리면 전부 초록이 나오고 아무것도 안 잰 것이 됩니다.'};

  const 화면안 = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.right > 0 && r.left < window.innerWidth;
  };
  /* 그 자리에서 **실제로 누름을 받는 것**이 이 요소인가. 덮여 있으면 거짓.
     **`pointer-events:none` 을 먼저 본다** — 그것이 걸리면 elementFromPoint
     가 그 **부모**를 돌려주고, 부모가 나를 담고 있으므로 「눌린다」 로
     읽혔다. 이 파일이 재려는 것이 정확히 「누르는 것이 실제로 눌리는가」
     라 아픈 구멍이었다 (2026-09-12 커밋 전 검토가 짚었다). */
  const 누를수있나 = el => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    if (getComputedStyle(el).pointerEvents === 'none') return false;
    const 위 = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!(위 && (위 === el || el.contains(위) || 위.contains(el)));
  };

  /* **열림과 닫힘은 서로의 반대가 아니다.** 사이드바는 0.18초 동안
     미끄러져 들어오고 나간다 — 그 사이에는 둘 다 아니다.
     「안 열렸다」 를 닫힘으로 쓰면 **아직 화면에 걸쳐 있는데 다음 줄이
     간다**: 실제로 그 때문에 「메뉴 단추가 무언가에 덮여 있다」 가 떴고,
     덮고 있던 것은 **닫히는 중인 사이드바 자신**이었다. 검사가 흔들린
     것이지 화면이 틀린 것이 아니다 (drawer.js 가 「기다리지 말고 본다」
     고 적어 둔 그 자리). */
  const 열렸나 = () => nav.getBoundingClientRect().left >= -1;
  const 닫혔나 = () => nav.getBoundingClientRect().right <= 0.5;

  // ── ① 로그인된 화면인가 ─────────────────────────────────────────
  const 나 = nav.querySelector('.sidefoot .who, .sidefoot');
  잰다(!!(나 && 나.textContent.trim()), ' 로그인된 화면 — 사이드바에 쓰는 사람이 적혀 있다',
       '사이드바 하단에 사용자 칸이 없다 (로그인 화면에서 돌린 것인지 보세요)');

  // ── ② 화면이 그려졌는가 ────────────────────────────────────────
  /* **그려지기 전의 「안 눌림」 과 가른다.** 사람이 본 것은 「화면은 멀쩡한데
     안 눌린다」 였다 — 본문이 비어 있으면 그건 다른 고장이다. */
  const 본문 = document.querySelector('main');
  잰다(!!(본문 && 본문.textContent.trim().length > 20 && 화면안(본문)),
       ' 본문이 그려졌다', '본문이 비어 있거나 화면 밖이다');

  /* **사람이 본 것은 「다른 것도 안 눌린다」 였다.** 사이드바만 재면 본문을
     덮는 다음 회귀는 이 눈에도 안 걸린다 — 실제로 그때 왼쪽 16px 띠가
     본문 위에 깔려 있었다(2026-09-12 커밋 전 검토가 이 항목이 없다고 짚었다). */
  const 본문링크 = 본문 ? [...본문.querySelectorAll('a[href]')].find(화면안) : null;
  if (!본문링크) {
    results.push('· 본문에 보이는 링크가 없어 본문 누름은 건너뜀');
  } else {
    잰다(누를수있나(본문링크), ` 본문의 링크(${본문링크.textContent.trim().slice(0, 12)})가 눌리는 자리에 있다`,
         '본문의 링크가 무언가에 덮여 있다 — 사이드바만의 고장이 아니다');
  }

  /* ── ③ 메뉴 단추가 눌리는가 ──────────────────────────────────────
     **재기 전에 접는다.** 앞 판이 연 채로 끝났으면 겹쳐 뜬 사이드바가
     토글을 덮고 있어서, 「무언가 위를 덮고 있다」 가 **점검이 남긴 자국**
     때문에 뜬다 — 자가시험을 돌린 바로 뒤에 실제로 그렇게 빨갰다.
     접는 것은 항목이 아니라 **판을 고르는 일**이라 세지 않는다. */
  if (!닫혔나()) {
    toggle.click();
    await 될때까지('처음 상태를 접는 것', 닫혔나);
  }

  잰다(닫혔나(), ' 처음에는 접혀 있다 — 좁은 화면은 본문이 다 쓴다',
       '누르기 전부터 사이드바가 열려 있다');

  잰다(누를수있나(toggle), ' 메뉴 단추가 눌리는 자리에 있다 (무엇에도 안 덮여 있다)',
       '메뉴 단추 자리에서 누름을 받는 것이 그 단추가 아니다 — 무언가 위를 덮고 있다');

  /* **단추의 두 이름이 같은가** (2026-09-13 에 사람이 정한 「메뉴 열기」).
     보이는 말(title)과 읽어 주는 이름(aria-label)이 갈리면 **화면 낭독기를
     쓰는 사람만 다른 이름을 듣습니다** — 화면을 보는 사람에게는 아무 표시도
     안 납니다. 글자를 문서에서 찾지 않고 **그려진 화면에서 뽑아** 견줍니다. */
  {
    const 보임 = (toggle.getAttribute('title') || '').trim();
    const 읽힘 = (toggle.getAttribute('aria-label') || '').trim();
    잰다(!!읽힘 && 보임 === 읽힘,
         ` 단추의 보이는 말과 읽어 주는 이름이 같다 (${읽힘 || '없음'})`,
         `단추의 두 이름이 갈렸다 — 보이는 말 「${보임}」 · 읽어 주는 이름 「${읽힘}」`);
  }

  /* **아이폰에서 「바깥을 눌러 닫기」 가 가려면 본문이 누를 수 있는 것처럼
     보여야 합니다** — 사파리는 그럴 때만 합성 클릭을 document 까지 올립니다.
     여기서 잴 수 있는 것은 **그 조건이 서 있는가**뿐입니다(`cursor`).
     **실제로 그 기기가 클릭을 올리는지는 이 눈으로 못 봅니다** — 크롬이
     흉내 내는 것은 폭·터치·호버까지이고 사파리의 그 규칙은 아닙니다.
     그 한 줄은 실기로만 닫힙니다 (봐둘것 AY-c · 인계). */
  /* **거는 조건과 재는 조건을 같은 것으로 둔다** — 갈리면 「걸어 두고 한 번도
     안 재는」 창이 생긴다. CSS 는 `(hover:none) and (pointer:coarse)` 다. */
  if (!matchMedia('(hover: none) and (pointer: coarse)').matches) {
    results.push('· 손가락 기기가 아니라 아이폰 쪽 조건은 건너뜀 (그 기기에는 이 규칙이 없다)');
  } else {
    잰다(getComputedStyle(document.body).cursor === 'pointer',
         ' 손가락 기기에서 본문이 누를 수 있는 것으로 보인다 (바깥 누름이 닫기까지 간다)',
         '손가락 기기인데 본문이 누를 수 없는 것으로 보인다 — 아이폰 사파리에서 바깥 누름이 document 까지 안 갈 수 있다');
  }

  toggle.click();
  const 열림 = await 될때까지('메뉴 단추를 눌러 사이드바가 열리는 것', 열렸나);
  /* **이 줄이 이 파일이 생긴 이유다.** 못 쟀음이 아니라 ✗ 다 — 「안 열린다」 는
     화면의 고장이고, 사람이 본 것이 정확히 이것이다. */
  잰다(열림, ' **메뉴 단추를 누르면 사이드바가 화면 안으로 들어온다**',
       '메뉴 단추를 눌러도 사이드바가 안 열린다 (휴대폰에서 아무 데도 못 간다)');

  // ── ④ 열린 사이드바에서 화면을 옮길 수 있는가 ──────────────────
  const 링크 = [...nav.querySelectorAll('nav a[href]')].filter(a => 화면안(a));
  if (!열림) {
    results.push('· 사이드바가 안 열려 화면 옮기기는 건너뜀');
  } else if (!링크.length) {
    results.push('· 사이드바에 보이는 링크가 없어 화면 옮기기는 건너뜀');
  } else {
    const 갈곳 = 링크.find(a => !a.hasAttribute('aria-current')) || 링크[0];
    잰다(누를수있나(갈곳), ` 사이드바 링크(${갈곳.textContent.trim()})가 눌리는 자리에 있다`,
         '사이드바 링크가 무언가에 덮여 있다');
    /* **정말로 옮기지는 않는다** — 옮기면 이 스크립트가 죽는다.
       재는 것은 **누름이 그 링크에 닿았는가**이고, 그래서 듣는 자리는
       링크 자신이다. document 캡처에서 들으면 중간에서 누가 전파를 끊어도
       이 줄이 먼저 돌아 초록이 난다 — 재려던 것을 안 재게 된다.

       **가려는 곳은 잠깐 갈아 끼운다.** 전파를 막는 고장에서는 우리 줄이
       아예 안 불리고, 그러면 `preventDefault` 도 못 한다 — 브라우저는
       그대로 옮겨 가고 점검은 거기서 죽는다. 자가시험 ③ 이 「놓침」 으로
       나온 것이 그것이었다: 검사가 못 잡은 것이 아니라 **끌려간 것**이다.
       주소를 같은 페이지 안(`#`)으로 바꿔 두면 어느 쪽이든 안 떠난다. */
    const 원래주소 = 갈곳.getAttribute('href');
    let 닿았나 = false;
    const 막기 = e => { 닿았나 = true; e.preventDefault(); };
    갈곳.setAttribute('href', '#점검');
    갈곳.addEventListener('click', 막기);
    try {
      갈곳.click();
      await sleep(60);
    } finally {
      갈곳.removeEventListener('click', 막기);
      갈곳.setAttribute('href', 원래주소);
    }
    const 잡은주소 = 닿았나 ? 원래주소 : null;
    잰다(!!잡은주소, ` 그 링크를 누르면 화면을 옮기려 한다 (${잡은주소 || '아무 데도'})`,
         '사이드바 링크를 눌러도 아무 주소로도 안 간다');
  }

  // ── ⑤ 닫는 길이 있는가 ─────────────────────────────────────────
  if (!열림) {
    results.push('· 사이드바가 안 열려 닫는 길 둘을 건너뜀');
  } else {
    toggle.click();
    잰다(await 될때까지('다시 눌러 닫히는 것', 닫혔나),
         ' 다시 누르면 닫힌다', '다시 눌러도 안 닫힌다 — 한 번 열면 본문을 덮은 채로 남는다');

    toggle.click();
    await 될때까지('바깥 누르기를 재려고 다시 여는 것', 열렸나);
    (본문 || document.body).click();
    잰다(await 될때까지('바깥을 눌러 닫히는 것', 닫혔나),
         ' 바깥을 누르면 닫힌다', '겹쳐 뜬 사이드바가 바깥을 눌러도 안 닫힌다');
  }

  // ── ⑥ 왼쪽 가장자리 띠가 본문의 누름을 가져가지 않는가 ─────────
  /* 그 띠는 **마우스를 대면 들춰 보는** 자리다(4-0). 손가락에는 호버가
     없으므로 그런 기기에서는 여는 길이 아니라 **본문 왼쪽을 덮고 누름만
     가져가는 자리**가 된다. 폭이 아니라 `hover` 로 가른다 — 좁은 창의
     노트북에서는 들춰 보기가 살아 있어야 한다. */
  const 띠 = $('sideedge');
  const 호버없음 = window.matchMedia('(hover: none)').matches;
  if (!띠) {
    results.push('· 이 화면에는 가장자리 띠가 없어 건너뜀');
  } else if (!호버없음) {
    results.push('· 이 기기에는 호버가 있어 가장자리 띠는 살아 있는 것이 맞다 — 건너뜀');
  } else {
    const 보임 = getComputedStyle(띠).display !== 'none';
    잰다(!보임, ' 호버가 없는 기기에서는 가장자리 띠가 본문을 안 덮는다',
         '호버가 없는데 가장자리 띠가 살아 있어 본문 왼쪽의 누름을 가져간다');
  }

  /* **끝까지 갔는가.** 점검이 한복판에서 죽으면 그때까지 잰 것만 남아
     「전부 통과」 로 보인다 — `통과: errors.length === 0` 만으로는 그것을
     못 가른다(11-3 2단계 · drawer.js 의 `완주` 와 같은 자리). 여기까지
     왔다는 것이 곧 끝까지 갔다는 뜻이고, 중간에 죽으면 아래 `.catch` 가
     `완주: false` 로 받는다. */
  const 완주 = true;
  const 잰것 = results.filter(r => /^[✓✗]/.test(r)).length;
  const 건너뜀 = results.filter(r => String(r).startsWith('·')).length;
  if (못쟀음.length) results.push(`? 못 쟀음 ${못쟀음.length}개 — 화면이 틀린 것이`
    + ' 아니라 이 판에서 답을 못 얻은 것입니다 (탭을 보이게 두고 다시 돌리세요)');
  console.table(results);
  return {폭, 통과: errors.length === 0 && 완주, 완주, 실패: errors,
          항목수: 잰것, 건너뜀, 못쟀음, 항목: results};
};

/* ── 자가시험 — 고장을 심어서 검사를 검사한다 ───────────────────────
   갈래마다 고장을 하나씩 심었다 걷어내며 **✗ 로 나오는지** 잽니다.
   통과나 「못 쟀음」 으로 나오면 거기가 검사가 새는 입구입니다.

   **① 이 2026-09-12 에 실제로 났던 그 고장입니다** — 토글이 `sidepin` 만
   붙이던 옛 동작. 고친 자리를 되돌려 심는 것이 가장 정확합니다. */
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
  {갈래: '① 옛 고장 — 토글이 sidepin 만 붙인다',
   나와야: '메뉴 단추를 누르면 사이드바가 화면 안으로 들어온다',
   심는다: () => {
     // 앱의 핸들러를 캡처에서 끊고, 그 자리에 **옛 동작**을 놓는다
     const 풀기 = 캡처막기(el => !!el.closest('#sidetoggle'));
     const f = e => {
       if (e.target instanceof Element && e.target.closest('#sidetoggle')) {
         document.body.classList.toggle('sidepin');   // 좁은 화면에서는 CSS 가 무시한다
       }
     };
     document.addEventListener('click', f, true);
     return () => { 풀기(); document.removeEventListener('click', f, true); };
   }},
  {갈래: '② 열려도 화면 밖에 있다',
   나와야: '메뉴 단추를 누르면 사이드바가 화면 안으로 들어온다',
   심는다: () => 스타일('.sidenav.peek{transform:translateX(-100%)!important}')},
  {갈래: '③ 사이드바 링크가 안 눌린다',
   나와야: '그 링크를 누르면 화면을 옮기려 한다',
   못심음: 항목 => 항목.some(r => String(r).includes('화면 옮기기는 건너뜀')),
   심는다: () => 캡처막기(el => !!(el.closest('#sidenav') && el.closest('a')))},
  {갈래: '④ 닫는 길이 없다',
   나와야: '다시 누르면 닫힌다',
   심는다: () => {
     const nav = document.getElementById('sidenav');
     const f = () => nav.classList.add('peek');       // 무엇을 눌러도 다시 열린다
     document.addEventListener('click', f);
     return () => document.removeEventListener('click', f);
   }},
  {갈래: '⑤ 메뉴 단추가 누름을 안 받는다 (pointer-events)',
   나와야: '메뉴 단추가 눌리는 자리에 있다',
   심는다: () => 스타일('.sidetoggle{pointer-events:none}')},
  {갈래: '⑥ 본문의 링크가 덮여 있다',
   나와야: '본문의 링크(',
   못심음: 항목 => 항목.some(r => String(r).includes('본문 누름은 건너뜀')),
   심는다: () => 스타일('main a{pointer-events:none}')},
  {갈래: '⑦ 단추의 두 이름이 갈린다',
   /* **나와야 는 항목의 라벨이다** — 실패 문구가 아니다. 자가시험은 `✗` 로
      시작하는 줄에서 찾는데 그 줄에 실리는 것이 라벨이다(2026-09-13 에
      자가시험이 이 둘을 「놓침」 으로 잡아 주어 알았다). */
   나와야: '단추의 보이는 말과 읽어 주는 이름이 같다',
   심는다: () => {
     const t = document.getElementById('sidetoggle');
     const 옛 = t.getAttribute('aria-label');
     t.setAttribute('aria-label', 옛 + ' (다른 이름)');
     return () => t.setAttribute('aria-label', 옛);
   }},
  {갈래: '⑧ 아이폰에서 바깥 누름이 안 닿는다',
   나와야: '손가락 기기에서 본문이 누를 수 있는 것으로 보인다',
   못심음: 항목 => 항목.some(r => String(r).includes('손가락 기기가 아니라')),
   심는다: () => 스타일('body{cursor:auto!important}')},
  {갈래: '⑨ 가장자리 띠가 본문을 덮는다',
   나와야: '가장자리 띠가 본문을 안 덮는다',
   못심음: 항목 => 항목.some(r => String(r).includes('가장자리 띠')
                          && String(r).startsWith('·')),
   심는다: () => 스타일('.sideedge{display:block!important}')},
];

/* **판마다 자리를 고르고 시작한다.** 앞 갈래의 판이 사이드바를 열어 둔 채
   끝나면 다음 판이 그 자국 위에서 돌아, **심지 않은 고장이 섞인다** —
   실제로 ③ 이 그것 때문에 「놓침」 으로 나왔다(그 갈래를 혼자 돌리면
   잡는다). 여는 길이 아니라 **판을 고르는 일**이라 클래스를 직접 걷고,
   여기서만 시간을 기다린다 — 재는 자리가 아니라 치우는 자리다. */
const 판정리 = async () => {
  const nav = document.getElementById('sidenav');
  if (nav) nav.classList.remove('peek');
  document.body.classList.remove('sidepin');
  if (!nav) return;
  /* **값이 아니라 조건으로 기다린다.** 처음에는 260ms 를 박아 두었는데,
     전환이 그보다 길어지면 다음 판의 첫 가드가 **닫는 대신 연다**(peek 는
     이미 걷혀서 토글이 여는 쪽으로 간다) — 한 판이 통째로 빨개진다.
     검사가 흔들리는 자리를 값으로 만들지 않는다 (drawer.js 의 그 교훈). */
  const 끝 = Date.now() + 1500;
  while (nav.getBoundingClientRect().right > 0.5 && Date.now() < 끝) {
    await new Promise(r => setTimeout(r, 25));
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
    if (것.못심음 && 것.못심음(깨끗.항목)) {
      못심음++;
      줄.push(`- ${것.갈래} — 이 화면·이 계정에 그 자리가 없어 **못 심음**`);
      continue;
    }
    await 판정리();
    const 걷기 = 것.심는다();
    let 결과;
    try { 결과 = await 점검(); } finally { 걷기(); await 판정리(); }
    const 잡았나 = !결과.치명 && (결과.실패 || []).some(f => String(f).length > 0)
                 && (결과.항목 || []).some(r => String(r).startsWith('✗') && String(r).includes(것.나와야));
    if (잡았나) { 잡음++; 줄.push(`✗ ${것.갈래} — 잡음`); }
    else { 놓침++; 줄.push(`! ${것.갈래} — **놓침** (심었는데 ✗ 가 안 났다)`); }
  }
  console.table(줄);
  return {자가시험: true, 잰것: 잡음, 놓친것: 놓침, 못심음, 안심으면초록: 깨끗.통과, 줄};
};

/* **죽은 채로 「통과」 를 내지 않는다.** 중간에 예외가 나면 여기서 받아
   `완주: false` 로 돌려준다 — 콘솔에 빨간 줄만 남고 결과가 없으면, 돌린
   사람은 「안 돌았다」 와 「돌았는데 초록」 을 구별하지 못한다. */
const 지킨다 = p => p.catch(e => ({완주: false, 통과: false,
  실패: ['점검이 중간에 죽었습니다: ' + (e && e.message ? e.message : e)]}));

return 지킨다(window.__자가시험 ? 자가시험() : 점검());
})()
