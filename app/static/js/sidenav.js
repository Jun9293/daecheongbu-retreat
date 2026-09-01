/* 사이드바 — 기본은 접힘, 여는 길이 둘이고 뜻이 다르다.
 *
 *   토글        고정해서 계속 연다. 본문이 그만큼 밀린다
 *   가장자리 호버  잠깐 들춰 본다. 본문은 그대로고 위에 겹쳐 뜬다
 *
 * 상단 탭 줄을 없앴으므로 화면 이동은 여기로만 한다. 그래서 "잠깐 들춰
 * 보기"가 있어야 한다 — 다른 화면으로 가려고 매번 고정했다 푸는 것은
 * 이동 한 번에 조작이 셋이다.
 *
 * 고정 여부는 기기에 남긴다. 매번 접힌 채로 시작하면 늘 쓰는 사람이
 * 매번 같은 클릭을 한다. 기본값은 접힘이고, 그건 한 번도 켠 적 없을 때다.
 */
(function () {
  "use strict";

  var KEY = "dcb.sidepin";
  var nav = document.getElementById("sidenav");
  var edge = document.getElementById("sideedge");
  var toggle = document.getElementById("sidetoggle");
  if (!nav) return;

  var peekTimer = null;

  function pinned() {
    return document.body.classList.contains("sidepin");
  }

  function setPinned(on) {
    document.body.classList.toggle("sidepin", !!on);
    if (toggle) toggle.setAttribute("aria-pressed", on ? "true" : "false");
    if (on) nav.classList.remove("peek");
    try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { /* 사생활 모드 */ }
    // 보드는 가로 격자를 픽셀로 그린다. 폭이 바뀌었으니 다시 재라고 알린다.
    dispatchEvent(new Event("resize"));
  }

  function peek(on) {
    if (pinned()) return;
    clearTimeout(peekTimer);
    if (on) {
      nav.classList.add("peek");
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

  if (toggle) {
    toggle.addEventListener("click", function () { setPinned(!pinned()); });
  }

  // 들춰 본 상태에서 바깥을 누르면 접는다 (고정한 상태는 건드리지 않는다)
  document.addEventListener("click", function (e) {
    if (pinned() || !nav.classList.contains("peek")) return;
    if (e.target.closest && (e.target.closest("#sidenav") || e.target.closest("#sidetoggle"))) return;
    nav.classList.remove("peek");
  });

  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { /* 무시 */ }
  if (saved === "1") setPinned(true);
})();
