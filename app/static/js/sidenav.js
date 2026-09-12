/* 사이드바 (B안 · 4-0) — ≥1280px 펼침 고정이 기본, 그 아래는 접힘.
 *
 *   토글(≥1280)   고정을 켜고 끈다. 본문이 그만큼 밀린다
 *   토글(그 아래)  겹쳐 연다. 밀 자리가 없으므로 고정이 화면을 못 바꾼다
 *   가장자리 호버  잠깐 들춰 본다. 본문은 그대로고 위에 겹쳐 뜬다 —
 *                 **호버가 없는 기기에는 이 길이 없다**(CSS 가 띠를 안 그린다)
 *
 * 1280px 아래에서는 CSS 가 sidepin 을 무시한다. 그래서 **좁은 화면에서는
 * 토글이 겹쳐 여는 쪽(peek)을 직접 켠다** — 그러지 않으면 누른 것이 아무
 * 화면도 안 바꾸고, 상단 탭 줄이 없어서 이동 수단이 통째로 없어진다.
 *
 * **호버로만 열던 시절에 휴대폰에서는 아무 데도 못 갔다** (2026-09-12).
 * 손가락에는 호버가 없는데 여는 길이 가장자리 호버뿐이었고, 토글은
 * sidepin 만 붙였다 — CSS 가 그것을 무시하니 「눌러도 아무 일이 없다」 였다.
 *
 * 고정 여부는 기기에 남긴다. 저장된 값이 없을 때만 화면 폭이 기본을
 * 정한다 (retreat_base.html 의 부팅 스크립트가 첫 그림 전에 읽는다).
 */
(function () {
  "use strict";

  var KEY = "dcb.sidepin";
  var nav = document.getElementById("sidenav");
  var edge = document.getElementById("sideedge");
  var toggle = document.getElementById("sidetoggle");
  if (!nav) return;

  var peekTimer = null;
  // **사람이 토글로 연 것인가.** 마우스가 떠나도 닫지 않으려고 든다 —
  // 좁은 창(마우스가 있는)에서 토글로 열면 곧바로 mouseleave 가 와서
  // 160ms 뒤에 저절로 닫혔다.
  var held = false;

  // 저장된 고정 값 그대로 — 토글은 이것을 뒤집는다. 화면 폭과 무관하다.
  function pinnedClass() {
    return document.body.classList.contains("sidepin");
  }

  function pinned() {
    // **화면에 실제로 고정돼 보이는가.** 1280px 아래에서는 CSS 가 sidepin 을
    // 무시한다 — 클래스가 붙어 있어도 화면은 접혀 있으므로, 여기서 참을
    // 돌려주면 들춰 보기(peek)가 막혀 이동 수단이 없어진다.
    return window.innerWidth >= 1280 && pinnedClass();
  }

  function setPinned(on) {
    document.body.classList.toggle("sidepin", !!on);
    if (toggle) toggle.setAttribute("aria-pressed", on ? "true" : "false");
    // 좁은 화면에서는 고정이 화면을 못 바꾸므로 peek 를 걷으면 그냥 닫힌다
    if (on && window.innerWidth >= 1280) nav.classList.remove("peek");
    try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { /* 사생활 모드 */ }
    // 보드는 가로 격자를 픽셀로 그린다. 폭이 바뀌었으니 다시 재라고 알린다.
    dispatchEvent(new Event("resize"));
  }

  function peek(on) {
    if (pinned()) return;
    clearTimeout(peekTimer);
    if (on) {
      nav.classList.add("peek");
    } else if (held) {
      return;                       // 손으로 연 것은 손으로 닫는다
    } else {
      // 사이드바와 가장자리 사이를 지날 때 깜빡이지 않게 조금 기다린다
      peekTimer = setTimeout(function () { nav.classList.remove("peek"); }, 160);
    }
  }

  if (edge) {
    edge.addEventListener("mouseenter", function () { peek(true); });
    edge.addEventListener("mouseleave", function () { peek(false); });
  }
  nav.addEventListener("mouseenter", function () { peek(true); });
  nav.addEventListener("mouseleave", function () { peek(false); });

  // 좁은 화면의 여닫기 — 고정이 화면을 못 바꾸므로 겹쳐 여는 쪽을 직접 켠다
  function 손으로(on) {
    held = !!on;
    clearTimeout(peekTimer);
    nav.classList.toggle("peek", !!on);
    if (toggle) toggle.setAttribute("aria-pressed", on ? "true" : "false");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      if (window.innerWidth >= 1280) {
        // 넓은 화면 — pinned() 가 아니라 **클래스 원값**을 뒤집는다. 좁은
        // 화면에서 pinned() 는 늘 거짓이라, 그걸 쓰면 토글이 '1' 만 쓰게 되고
        // 넓은 화면에서 손으로 접어 둔 '0' 을 좁은 창이 아무 표시 없이 덮어쓴다.
        held = false;
        setPinned(!pinnedClass());
      } else {
        // 좁은 화면 — **고정값(localStorage)은 건드리지 않는다.** 여기서 쓰면
        // 휴대폰에서 한 번 연 것이 다음에 노트북을 열었을 때의 기본이 된다.
        손으로(!nav.classList.contains("peek"));
      }
    });
  }

  /* **창이 넓어지면 손으로 연 표시를 내려놓는다.** 좁은 화면에서 토글로
     연 채 창을 넓히면 `pinned()` 는 여전히 거짓인데 `held` 가 참이라
     **마우스를 떼도 안 닫힌다** — 들춰 보기의 뜻이 그 창에서만 달라진다
     (2026-09-12 커밋 전 검토). 닫지는 않는다: 열어 둔 것을 창 크기가
     멋대로 접으면 그것대로 놀란다. */
  addEventListener("resize", function () {
    if (window.innerWidth >= 1280) held = false;
  });

  // 들춰 본 상태에서 바깥을 누르면 접는다 (고정한 상태는 건드리지 않는다)
  document.addEventListener("click", function (e) {
    if (pinned() || !nav.classList.contains("peek")) return;
    if (e.target.closest && (e.target.closest("#sidenav") || e.target.closest("#sidetoggle"))) return;
    held = false;
    nav.classList.remove("peek");
  });

  // 저장된 고정 여부는 **첫 그림 전에** retreat_base.html 의 짧은 스크립트가
  // 이미 붙였다. 여기서 다시 붙이면 그린 뒤에 붙는 셈이라, 화면을 옮길 때마다
  // 사이드바와 본문이 밀려 들어온다. 버튼 상태만 맞춰 둔다.
  if (toggle) toggle.setAttribute("aria-pressed", pinnedClass() ? "true" : "false");
})();
