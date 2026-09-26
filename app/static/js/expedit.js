/* 지출 「전체 편집」 (CLAUDE.md 7-4 · 2026-09-26 사람이 정한 확정본).
 *
 * **예산 화면과 같은 방식**이다 — 줄마다 「고치기」 를 펴지 않고 단추 하나로
 * 표 전체를 편집 상태로 바꾸고, 저장도 `POST /expenses/bulk` 한 번이다.
 *
 * 예산 표와 달리 **다시 그리지 않고 그 자리에서 칸만 바꾼다** — 여기서는 줄을
 * 옮기지 않아 병합이 달라질 일이 없다. 바꾸는 것이 적을수록 갈릴 자리도 적다.
 *
 * 편집 상태에서만 줄 끝에 칸이 하나 는다 — **예산 항목과 「취소」** 다.
 * 예산 항목은 묶음의 머리 칸이라 그 자리에서 못 고친다(고치면 그 줄이 다른
 * 묶음으로 가야 한다).
 */
(function () {
  'use strict';

  var 단추 = document.getElementById('expedit');
  var 띠 = document.getElementById('expbar');
  var 말 = document.getElementById('expmsg');
  var 저장 = document.getElementById('expsave');
  var 되돌림 = document.getElementById('expcancel');
  var 항목씨앗 = document.getElementById('exp-cats');
  if (!단추 || !띠) return;

  var 항목들 = JSON.parse((항목씨앗 && 항목씨앗.textContent) || '[]');
  var 켬 = false;
  var 뺀것 = [];

  function esc(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function 콤마(v) {
    var n = parseInt(String(v == null ? '' : v).replace(/[^0-9-]/g, ''), 10);
    return isNaN(n) ? '' : n.toLocaleString('ko-KR');
  }
  function 수(v) {
    var t = String(v == null ? '' : v).replace(/[^0-9-]/g, '');
    return t === '' ? 0 : parseInt(t, 10);
  }
  function 줄들() {
    return Array.prototype.slice.call(
      document.querySelectorAll('table.exptbl tr[data-exp][data-edit="1"]'));
  }

  /* 칸 하나를 입력으로 바꾼다 — **원래 내용을 들고 있다가** 되돌린다.
     되돌리기가 화면을 다시 읽어 오면 방금 친 것과 옛 값이 섞인다 */
  function 칸바꾸기(td, html) {
    if (td.dataset.was === undefined) td.dataset.was = td.innerHTML;
    td.innerHTML = html;
  }
  function 칸되돌리기(td) {
    if (td.dataset.was !== undefined) {
      td.innerHTML = td.dataset.was;
      delete td.dataset.was;
    }
  }

  function 켠다() {
    document.querySelectorAll('table.exptbl').forEach(function (표) {
      표.classList.add('editing');
      var 머리 = 표.querySelector('thead tr');
      if (머리 && !머리.querySelector('.edith')) {
        var th = document.createElement('th');
        th.className = 'edith';
        th.textContent = '예산 항목 · 취소';
        머리.appendChild(th);
      }
      /* 못 고치는 줄에도 빈 칸을 하나 더한다 — 안 그러면 그 줄만 칸 수가 모자라
         표가 밀린다(남의 부서 줄과 취소된 줄이 그렇다) */
      표.querySelectorAll('tbody tr[data-exp]').forEach(function (tr) {
        var td = document.createElement('td');
        td.className = 'editcell';
        tr.appendChild(td);
      });
      표.querySelectorAll('tbody tr.longrow').forEach(function (tr) {
        var td = document.createElement('td');
        td.className = 'editcell';
        tr.appendChild(td);
      });
    });

    /* **병합된 칸은 그 묶음의 모든 줄에 같은 값이다** (2026-09-26 두 번째 검토 [2]) —
       세부항목-2 는 묶음의 첫 줄에만 입력칸이 있으므로, 그 칸을 고치면 묶음이
       통째로 바뀌어야 한다. 안 그러면 고친 이름이 첫 줄에만 붙어 묶음이 쪼개진다
       (예산 화면이 같은 자리에서 이미 그렇게 한다) */
    var 묶음 = -1;
    줄들().forEach(function (tr) {
      if (tr.querySelector('td.l3b')) 묶음 += 1;
      tr.dataset.blk = String(묶음);
    });

    줄들().forEach(function (tr) {
      var 칸 = tr.querySelectorAll('td');
      // 일자 · 영수증 금액 — 자리로 찾지 않고 **클래스로** 찾는다(세부항목-3 이
      // 있는 줄과 없는 줄의 칸 수가 다르다 · 4-18 이 머리글에서 한 그 판단)
      var 일자칸 = tr.querySelector('td.mono.nowrap');
      if (일자칸) 칸바꾸기(일자칸,
        '<input type="date" class="ei" data-f="date" value="' + esc(tr.dataset.date) + '">');
      var 금액칸 = tr.querySelectorAll('td.r.mono')[0];
      if (금액칸) 칸바꾸기(금액칸,
        '<input class="ei r mono" data-f="amount" inputmode="numeric" value="' +
        콤마(tr.dataset.amount) + '">');
      var l3b = tr.querySelector('td.l3b');
      if (l3b) 칸바꾸기(l3b, '<input class="ei" data-f="l3b" value="' + esc(tr.dataset.l3b) + '">');
      var 지출자 = tr.querySelector('td.payercell');
      if (지출자) {
        var 계좌 = 지출자.querySelector('.payer.acct');
        var html = '<input class="ei" data-f="payer" value="' + esc(tr.dataset.payer) + '">';
        /* **계좌를 볼 수 있는 사람에게만** 계좌 칸을 그린다 — 비어 있는 줄에도
           그려야 새로 적을 수 있다. 못 보는 사람에게는 칸 자체가 없고, 서버도
           그 사람이 보낸 계좌 칸을 안 받는다(`한줄을_고친다` 의 그 자리) */
        if (지출자.dataset.acctedit === '1') {
          html += '<input class="ei" data-f="bank" placeholder="은행" value="' +
            esc(계좌 ? 계좌.dataset.bank : '') + '">' +
            '<input class="ei mono" data-f="acctno" placeholder="계좌번호" value="' +
            esc(계좌 ? 계좌.dataset.no : '') + '">' +
            '<input class="ei" data-f="holder" placeholder="예금주" value="' +
            esc(계좌 ? 계좌.dataset.holder : '') + '">';
        }
        칸바꾸기(지출자, html);
      }
      var 지급 = tr.querySelectorAll('td')[칸.length - 2];
      if (지급) 칸바꾸기(지급,
        '<label class="epaid"><input type="checkbox" class="ei" data-f="paid"' +
        (tr.dataset.paid === '1' ? ' checked' : '') + '> 지급</label>');

      var 끝 = tr.querySelector('td.editcell');
      if (끝) {
        var opts = '<option value="">미지정</option>';
        항목들.forEach(function (c) {
          opts += '<option value="' + c.id + '"' +
            (String(c.id) === tr.dataset.cat ? ' selected' : '') + '>' + esc(c.name) + '</option>';
        });
        끝.innerHTML = '<select class="ei" data-f="cat">' + opts + '</select>' +
          '<button type="button" class="sbtn expout" title="이 지출을 취소한다 — 행은 흐리게 남는다">취소</button>';
      }
    });
  }

  function 끈다(다시읽나) {
    if (다시읽나) { location.reload(); return; }
    document.querySelectorAll('table.exptbl').forEach(function (표) {
      표.classList.remove('editing');
      var th = 표.querySelector('thead .edith');
      if (th) th.remove();
      표.querySelectorAll('td.editcell').forEach(function (td) { td.remove(); });
      표.querySelectorAll('td[data-was]').forEach(칸되돌리기);
      /* 취소 표시도 함께 걷는다 (2026-09-26 검토 [M]) — 안 걷으면 「되돌리기」 를
         누른 줄이 **취소된 것처럼 보이는 채로** 남아, 화면이 저장된 값과 다른
         것을 보여준다 */
      표.querySelectorAll('tr.willcancel').forEach(function (tr) {
        tr.classList.remove('willcancel');
      });
    });
  }

  function 상태(on) {
    켬 = on;
    띠.hidden = !on;
    단추.textContent = on ? '편집 끄기' : '전체 편집';
    단추.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (말) 말.textContent = '';
  }

  단추.addEventListener('click', function () {
    if (켬) { 끈다(false); 뺀것 = []; 상태(false); }
    else { 켠다(); 상태(true); }
  });
  if (되돌림) 되돌림.addEventListener('click', function () {
    끈다(false); 뺀것 = []; 상태(false);
  });

  document.addEventListener('click', function (e) {
    var out = e.target.closest && e.target.closest('.expout');
    if (!out || !켬) return;
    var tr = out.closest('tr[data-exp]');
    if (!tr) return;
    /* 취소는 **저장할 때** 간다 — 누르자마자 보내면 「되돌리기」 가 거짓이 된다 */
    var id = parseInt(tr.dataset.exp, 10);
    if (뺀것.indexOf(id) < 0) 뺀것.push(id);
    tr.classList.add('willcancel');
    out.textContent = '취소함';
    out.disabled = true;
  });

  /* 금액은 편집 중에도 천 단위 콤마 (예산 화면과 같은 자리) */
  document.addEventListener('input', function (e) {
    var el = e.target;
    if (!el.dataset || el.dataset.f !== 'amount') return;
    var 끝 = el.selectionStart === el.value.length;
    var v = 콤마(el.value);
    if (v !== el.value) {
      el.value = v;
      if (끝) el.setSelectionRange(v.length, v.length);
    }
  });

  if (저장) 저장.addEventListener('click', function () {
    저장.disabled = true;
    if (말) 말.textContent = '저장하는 중…';
    /* 묶음마다 세부항목-2 의 지금 값 — 입력칸이 없는 줄이 이것을 함께 싣는다 */
    var 묶음값 = {};
    줄들().forEach(function (tr) {
      var el = tr.querySelector('[data-f="l3b"]');
      if (el) 묶음값[tr.dataset.blk] = el.value;
    });
    var rows = 줄들().filter(function (tr) {
      return 뺀것.indexOf(parseInt(tr.dataset.exp, 10)) < 0;
    }).map(function (tr) {
      /* **없는 칸은 아예 안 싣는다** — 표는 칸을 세로로 병합하므로 묶음의 첫
         줄에만 있는 칸이 있다(세부항목-2). 빈 글자를 실어 보내면 서버가
         「지우라」 로 읽어 그 값이 **말없이 사라진다**(2026-09-26 검토 [B]).
         비고와 인원도 같은 까닭으로 안 싣는다 — 비고는 팝업에서 고치고(7-4)
         인원은 명단 이름 수다(7-2) */
      var 줄 = {id: parseInt(tr.dataset.exp, 10)};
      function 싣는다(키, f, 바꿈) {
        var el = tr.querySelector('[data-f="' + f + '"]');
        if (el) 줄[키] = 바꿈 ? 바꿈(el.value) : el.value;
      }
      싣는다('expense_date', 'date');
      싣는다('amount', 'amount', 수);
      싣는다('budget_category_id', 'cat');
      싣는다('level3b', 'l3b');
      /* 입력칸이 없는 줄(병합 안쪽)도 **묶음의 값**을 싣는다 — 안 보내면 옛
         이름으로 남아 묶음이 쪼개진다(검토 [2]). 「안 보낸 칸은 안 고친다」 는
         **화면에 그 칸이 아예 없을 때**의 규약이고, 여기는 있는 값이다 */
      if (줄.level3b === undefined && 묶음값[tr.dataset.blk] !== undefined) {
        줄.level3b = 묶음값[tr.dataset.blk];
      }
      싣는다('payer_name', 'payer');
      싣는다('payer_bank', 'bank');
      싣는다('payer_account_number', 'acctno');
      싣는다('payer_account_holder', 'holder');
      var paid = tr.querySelector('[data-f="paid"]');
      줄.paid = !!(paid && paid.checked);
      return 줄;
    });
    fetch('/expenses/bulk', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({rows: rows, removed: 뺀것})
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || ('저장하지 못했습니다 (' + r.status + ')'));
        return j;
      });
    }).then(function () {
      location.reload();
    }).catch(function (err) {
      /* **편집 상태를 그대로 둔다** — 되돌리면 방금 친 것이 사라진다 */
      저장.disabled = false;
      if (말) 말.textContent = String(err.message || err);
    });
  });
})();
