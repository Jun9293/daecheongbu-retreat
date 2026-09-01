/* 잠깐 떴다 사라지는 안내 (`.flash`).
 *
 * 로그인 직후의 "○○님, 환영합니다." 가 보드 하단에 계속 떠 있었다.
 * 이 배너는 서버가 쿠키로 한 번 보내고 마는 것이라 화면을 다시 그릴 일이
 * 없고, 그래서 아무도 지우지 않으면 그 페이지에 있는 내내 남는다.
 *
 * 두 가지로 지운다 — 시간이 지나면 저절로, 그리고 눌러서 바로.
 * 눌러서 닫는 길이 없으면 무언가를 가리고 있을 때 치울 방법이 없다.
 *
 * 이 파일을 따로 둔 이유: 예전에는 app.js 안에만 있어서 app.css 쪽 화면
 * (홈·지출 등)에서만 사라지고, 보드·마법사 쪽은 계속 떠 있었다.
 * 같은 것이 두 벌이 아니라 한 벌이어야 두 화면이 같이 동작한다.
 */
(function () {
  "use strict";

  var LINGER = 4500;   // 읽을 시간은 주되 오래 두지 않는다
  var FADE = 320;

  function dismiss(el) {
    if (!el || el.dataset.going) return;
    el.dataset.going = "1";
    el.style.transition = "opacity " + FADE + "ms, transform " + FADE + "ms";
    el.style.opacity = "0";
    el.style.transform = getComputedStyle(el).transform === "none"
      ? "translateY(8px)" : "translate(-50%, 8px)";
    setTimeout(function () { el.remove(); }, FADE);
  }

  function arm(el) {
    if (!el || el.dataset.armed) return;
    el.dataset.armed = "1";
    el.setAttribute("title", "눌러서 닫기");
    el.style.cursor = "pointer";
    el.addEventListener("click", function () { dismiss(el); });
    setTimeout(function () { dismiss(el); }, LINGER);
  }

  function scan() {
    document.querySelectorAll(".flash").forEach(arm);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scan);
  } else {
    scan();
  }
})();
