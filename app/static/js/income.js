/* 수입 화면 (CLAUDE.md 7-6).
 *
 * 하는 일이 둘뿐이다 — 입금 줄을 눌러 그 자리에서 펼치는 것과, 고른 캡처
 * 이름을 보여 주는 것. **저장은 보통 폼이 한다** — 자바스크립트가 죽어도
 * 고칠 수 있어야 하고, 그러면 되돌림·실패 처리를 여기서 또 짤 일이 없다.
 *
 * 줄을 팝업이 아니라 **그 자리에서 펼치는** 까닭은 4-14 가 목록에서 정한 그
 * 모양이기 때문이다. 팝업으로 두면 뜨는 자리·화면 밖으로 안 나가게 미는 규칙·
 * 바깥 누름 판정이 지출 화면의 팝업(exppop.js)과 두 벌이 되고, 갈린 쪽을
 * 아무도 눈치채지 못한다.
 */
(function () {
  'use strict';

  var 표 = document.getElementById('deptbl');

  function 편집줄(id) {
    return 표 && 표.querySelector('tr.deprowedit[data-editof="' + id + '"]');
  }

  function 편다(행) {
    var 줄 = 편집줄(행.dataset.dep);
    if (!줄) return;                       /* 못 고치는 사람에게는 아예 없다 */
    var 열림 = !줄.hidden;
    /* 한 번에 하나만 편다 — 여럿이 열려 있으면 어느 줄을 저장하는지 흐려진다 */
    Array.prototype.forEach.call(표.querySelectorAll('tr.deprowedit'), function (t) {
      t.hidden = true;
    });
    Array.prototype.forEach.call(표.querySelectorAll('tr.deprow'), function (t) {
      t.classList.remove('open');
    });
    if (!열림) {
      줄.hidden = false;
      행.classList.add('open');
      var 첫칸 = 줄.querySelector('input[name="fee_amount"], button');
      if (첫칸) 첫칸.focus();
    }
  }

  if (표) {
    표.addEventListener('click', function (e) {
      /* 편집 줄 안(라디오·입력칸·단추)에서 누른 것은 펼치고 접는 일이 아니다 */
      if (e.target.closest('tr.deprowedit')) return;
      var 행 = e.target.closest('tr.deprow');
      if (행 && 행.dataset.dep) 편다(행);
    });
    표.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var 행 = e.target.closest && e.target.closest('tr.deprow');
      if (!행 || !행.dataset.dep) return;
      e.preventDefault();
      편다(행);
    });
  }

  /* 캡처는 고르자마자 보내지 않는다 — 잘못 고른 것을 무르려면 보내기 전에
     이름이 보여야 한다. 몇 분이 걸릴 수 있어 누른 뒤에는 다시 못 누르게 한다 */
  var 칸 = document.getElementById('capfile');
  var 이름 = document.getElementById('capname');
  var 보내기 = document.getElementById('capsend');
  var 폼 = document.getElementById('capform');
  if (칸 && 이름 && 보내기) {
    칸.addEventListener('change', function () {
      var f = 칸.files && 칸.files[0];
      이름.textContent = f ? f.name : '';
      보내기.hidden = !f;
    });
  }
  if (폼 && 보내기) {
    폼.addEventListener('submit', function () {
      보내기.disabled = true;
      보내기.textContent = '읽는 중…';
      if (이름) 이름.textContent = '캡처를 읽고 있습니다 — 몇십 초 걸릴 수 있습니다.';
    });
  }
})();
