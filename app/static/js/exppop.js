/* 지출 표의 팝업 (CLAUDE.md 7-4 · 2026-09-26 사람이 정한 확정본).
 *
 * 세 가지가 **한 부품**을 쓴다 — 긴 내용(명단·비고) · 계좌 · 영수증.
 * 뜨는 자리·닫는 규칙이 세 벌이 되면 갈린 쪽을 아무도 눈치채지 못한다
 * (4-14 가 상태·담당자 메뉴를 한 곳에 둔 그 까닭).
 *
 * 저장은 **누르는 것이 있어야** 일어난다 — 팝업에서 고치고 「저장」 을 눌러야
 * 반영된다. 실패하면 **팝업을 열어 둔 채 그 자리에 까닭을 적는다**: 조용히
 * 닫으면 고친 줄 알고 넘어간다(5-0 과 같은 자리).
 */
(function () {
  'use strict';

  if (!document.querySelector('table.exptbl')) return;

  var 팝 = null, 주인 = null, 닫기예약 = 0;

  function esc(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function 닫는다() {
    clearTimeout(닫기예약);
    if (팝) 팝.remove();
    팝 = null; 주인 = null;
  }
  /* 대상 아래 4px · **화면 밖으로 안 나간다** — 가로·세로 둘 다 잡는다
     (한쪽만 잡으면 나머지로 넘친다 · 4-14 의 그 자리) */
  function 띄운다(anchor, html, cls) {
    if (팝 && 주인 === anchor) { clearTimeout(닫기예약); return 팝; }
    닫는다();
    팝 = document.createElement('div');
    팝.className = 'exppop ' + (cls || '');
    팝.innerHTML = html;
    document.body.appendChild(팝);
    주인 = anchor;
    var r = anchor.getBoundingClientRect();
    var w = 팝.offsetWidth, h = 팝.offsetHeight;
    var top = r.bottom + 4;
    if (top + h > innerHeight - 8) top = Math.max(8, r.top - 4 - h);
    if (top + h > innerHeight - 8) top = Math.max(8, innerHeight - 8 - h);
    팝.style.top = Math.round(top) + 'px';
    팝.style.left = Math.round(Math.max(8, Math.min(r.left, innerWidth - 8 - w))) + 'px';
    팝.addEventListener('mouseenter', function () { clearTimeout(닫기예약); });
    팝.addEventListener('mouseleave', function () {
      if (팝 && 팝.dataset.hover === '1') 닫기예약 = setTimeout(닫는다, 160);
    });
    return 팝;
  }
  /* **편집 중에는 팝업을 안 연다** (2026-09-26 검토 [I]) — 이 팝업들은 저장하면
     화면을 다시 읽으므로, 아직 저장 안 한 칸이 통째로 사라진다. 아무 말 없이
     사라지면 고친 줄 알고 넘어간다(5-0 의 그 자리) */
  function 편집중() { return !!document.querySelector('table.exptbl.editing'); }

  /* **그 누름이 어느 지출 줄의 것인가** — 긴 내용 칸은 지출 줄 안에 없고
     아래에 따로 서는 줄(`tr.longrow[data-of]`)에 있다. `closest('tr[data-exp]')`
     만 보면 그 자리는 늘 `null` 이라 **권한 판정이 통째로 새어** 편집 중
     막기가 안 걸렸다(2026-09-26 화면 점검이 잡았다 · 봐둘것 BJ-i). */
  function 그줄(el) {
    var 긴줄 = el.closest('tr.longrow');
    if (긴줄) return document.querySelector('tr[data-exp="' + 긴줄.dataset.of + '"]');
    return el.closest('tr[data-exp]');
  }

  function 콤마(v) {
    var n = parseInt(String(v == null ? '' : v).replace(/[^0-9-]/g, ''), 10);
    return isNaN(n) ? '' : n.toLocaleString('ko-KR');
  }
  function 말한다(글) {
    if (!팝) return;
    var s = 팝.querySelector('.popmsg');
    if (s) s.textContent = 글;
  }

  /* 다른 곳을 누르면 닫는다. **팝업 안은 뺀다** — 안 그러면 글자를 고르는 순간 닫힌다 */
  addEventListener('pointerdown', function (e) {
    if (팝 && !(e.target instanceof Element && e.target.closest('.exppop'))) 닫는다();
  }, true);
  addEventListener('keydown', function (e) { if (e.key === 'Escape') 닫는다(); });
  addEventListener('scroll', function () { if (팝) 닫는다(); }, true);

  /* ── 계좌 — 이름에 마우스를 올리면 뜨고, 팝업으로 옮기면 유지된다.
        휴대폰은 눌러서 열고 다른 곳을 눌러 닫는다 (2026-09-26 확정본) ── */
  function 계좌팝(btn) {
    var 번호 = btn.dataset.no || '';
    var p = 띄운다(btn,
      '<div class="poprow"><b>' + esc(btn.dataset.bank || '은행 미입력') + '</b></div>' +
      '<div class="poprow mono">' + esc(번호 || '계좌번호 없음') +
      (번호 ? ' <button type="button" class="sbtn acctcopy" data-copy="' + esc(번호) + '">복사</button>' : '') +
      '</div>' +
      (btn.dataset.holder ? '<div class="poprow dim">예금주 ' + esc(btn.dataset.holder) + '</div>' : ''),
      'acctpop');
    if (p) p.dataset.hover = '1';
  }
  document.addEventListener('mouseover', function (e) {
    var btn = e.target.closest && e.target.closest('.payer.acct');
    if (btn) 계좌팝(btn);
  });
  document.addEventListener('mouseout', function (e) {
    var btn = e.target.closest && e.target.closest('.payer.acct');
    if (btn && 팝 && 주인 === btn) 닫기예약 = setTimeout(닫는다, 160);
  });

  /* ── 긴 내용(명단 · 비고) — 전체를 보이고, 고칠 수 있으면 그 자리에서 고친다 ── */
  function 긴팝(btn) {
    var 고칠수있나 = btn.dataset.edit === '1';
    var 이름 = btn.dataset.long === 'attendees' ? '참석자 명단' : '비고';
    var html = '<div class="poprow"><b>' + esc(이름) + '</b></div>';
    if (고칠수있나) {
      html += '<textarea class="popedit" rows="4">' + esc(btn.dataset.full) + '</textarea>' +
        '<div class="poprow"><span class="popmsg hint"></span>' +
        '<button type="button" class="sbtn p popsave">저장</button></div>';
      if (btn.dataset.long === 'attendees') {
        html += '<div class="poprow dim">인원은 이름 수로 셉니다 — 저장하면 지원금액도 다시 셉니다.</div>';
      }
    } else {
      html += '<div class="poprow full">' + esc(btn.dataset.full) + '</div>';
    }
    띄운다(btn, html, 'longpop');
  }

  function 긴칸저장(btn) {
    var ta = 팝 && 팝.querySelector('.popedit');
    var 단추 = 팝 && 팝.querySelector('.popsave');
    if (!ta || !단추) return;
    단추.disabled = true;
    말한다('저장하는 중…');
    var body = new URLSearchParams();
    body.set('kind', btn.dataset.long);
    body.set('value', ta.value);
    fetch('/expenses/' + btn.dataset.id + '/long', {
      method: 'POST', body: body,
      headers: {'Content-Type': 'application/x-www-form-urlencoded'}
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || ('저장하지 못했습니다 (' + r.status + ')'));
        return j;
      });
    }).then(function () {
      /* 지원금액·개인부담이 함께 바뀌므로 칸 몇 개만 고치지 않고 다시 읽는다 —
         화면에서 몇 칸만 고치면 위의 합계 카드가 옛 값으로 남는다 */
      location.reload();
    }).catch(function (err) {
      단추.disabled = false;
      말한다(String(err.message || err));
    });
  }

  /* ── 영수증 — 칩을 누르면 보이고, 거기서 더 붙이고 뗀다 ── */
  function 영수증팝(btn) {
    var 파일 = btn.dataset.file, 번호 = btn.dataset.no;
    var 줄 = btn.closest('tr');
    var 고칠수있나 = 줄 && 줄.dataset.edit === '1';
    var html = '<div class="poprow"><b>영수증 ' + esc(번호) + '</b>' +
      (btn.dataset.orig ? ' <span class="dim">· 원본 ' + esc(btn.dataset.orig) + '</span>' : '') +
      (parseInt(btn.dataset.uses, 10) > 1 ? ' <span class="dim">· 지출 ' + esc(btn.dataset.uses) + '건</span>' : '') +
      '</div>';
    /* **예산 항목과 금액을 함께 낸다** (2026-09-26 확정본) — 영수증을 열어 놓고
       「이 줄이 맞나」 를 한눈에 보려는 자리라, 그 둘이 없으면 다시 표로 눈을
       옮겨야 한다. 값은 **그 줄이 들고 있는 것**을 읽는다 — 팝업이 따로 세지 않는다 */
    if (줄) {
      var 항목 = 줄.closest('table');
      항목 = 항목 && 항목.querySelector('td.catcell');
      html += '<div class="poprow dim">' +
        (항목 ? esc(항목.textContent.trim()) + ' · ' : '') +
        '영수증 금액 ' + 콤마(줄.dataset.amount) + '원</div>';
    }
    if (파일) {
      html += '<a class="rcptview" href="' + esc(파일) + '" target="_blank">' +
        '<img src="' + esc(파일) + '" alt="영수증 ' + esc(번호) + '"></a>';
    } else {
      html += '<div class="poprow dim">' + esc(btn.dataset.memo || '파일 없이 메모만 있는 영수증입니다.') + '</div>';
    }
    if (고칠수있나) {
      /* **원본 번호는 여기서 고친다** (2026-09-26 검토 [F]) — 줄마다의 「고치기」
         폼이 없어지면서 고칠 자리가 화면에서 사라졌는데 CLAUDE.md 7-4 는 여전히
         고칠 수 있다고 적고 있었다. 사람이 매긴 번호라 자동 번호와 따로다 */
      html += '<div class="poprow"><input class="rorig" placeholder="원본 번호 (없으면 비움)" value="' +
        esc(btn.dataset.orig || '') + '">' +
        '<button type="button" class="sbtn rorigsave" data-exp="' + esc(btn.dataset.exp) +
        '" data-rcpt="' + esc(btn.dataset.rcpt) + '">번호 저장</button></div>';
      html += '<div class="poprow"><button type="button" class="sbtn rcptmore" data-exp="' +
        esc(btn.dataset.exp) + '">영수증 추가</button>' +
        '<button type="button" class="sbtn rcptdel" data-exp="' + esc(btn.dataset.exp) +
        '" data-rcpt="' + esc(btn.dataset.rcpt) + '">영수증 삭제</button></div>' +
        /* 「삭제」 라고 적지만 하는 일은 **이 지출에서 떼는 것**이다 — 영수증 행은
           남는다(0장 · 7-4). 말과 하는 일이 다르면 한 줄로 밝힌다 */
        '<div class="poprow dim">「삭제」 는 이 지출에서 떼는 것입니다 — 영수증은 남고 번호로 다시 이을 수 있습니다.</div>' +
        '<div class="poprow"><span class="popmsg hint"></span></div>';
    }
    띄운다(btn, html, 'rcptpop');
  }

  /* 새 영수증 올리기 — **영수증이 없는 줄의 「+ 첨부」 는 이것뿐**이다.
     이미 있는 영수증에 잇는 것(번호로 잇기)은 그 영수증 팝업의 「영수증 추가」 다 */
  function 올리기팝(anchor, expId, 번호로도) {
    var html = '<div class="poprow"><b>영수증 올리기</b></div>' +
      '<div class="poprow"><input type="file" class="rfile" accept="image/*,.pdf"></div>' +
      '<div class="poprow"><input class="rmemo" placeholder="또는 메모 (예: 결산 파일에 별첨)"></div>' +
      '<div class="poprow"><input class="rorig" placeholder="원본 번호 (없으면 비움)"></div>' +
      '<div class="poprow"><span class="popmsg hint"></span>' +
      '<button type="button" class="sbtn p rupload" data-exp="' + esc(expId) + '">올리기</button></div>';
    if (번호로도) {
      html += '<div class="poprow dim">이미 올린 영수증이면 번호로 잇습니다 — 새 번호를 주지 않습니다.</div>' +
        '<div class="poprow"><input class="rno" inputmode="numeric" placeholder="이미 있는 영수증 번호">' +
        '<button type="button" class="sbtn rlink" data-exp="' + esc(expId) + '">번호로 잇기</button></div>';
    }
    띄운다(anchor, html, 'rcptpop');
  }

  function 보낸다(url, body, 단추) {
    if (단추) 단추.disabled = true;
    말한다('보내는 중…');
    return fetch(url, {method: 'POST', body: body, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) {
        if (!r.ok && r.status !== 303) {
          return r.text().then(function (t) {
            var 말 = '';
            try { 말 = JSON.parse(t).detail; } catch (x) {}
            throw new Error(말 || ('보내지 못했습니다 (' + r.status + ')'));
          });
        }
        location.reload();
      }).catch(function (err) {
        if (단추) 단추.disabled = false;
        말한다(String(err.message || err));
      });
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!(t instanceof Element)) return;

    var 긴 = t.closest('.longcell');
    var 칩0 = t.closest('.rcptchip'), 첨부0 = t.closest('.rcptadd'), 더0 = t.closest('.rcptmore');
    /* **막는 것은 「고칠 수 있는 줄」 뿐이다** (2026-09-26 두 번째 검토 [10]) —
       남의 부서·취소된 줄의 팝업은 저장 단추가 없는 보기 전용이라 편집을 버릴
       일이 없다. 막는 규칙을 「저장이 일어날 수 있나」 로 좁힌다 */
    var 누른줄 = (긴 || 칩0 || 첨부0 || 더0);
    var 고칠수있는줄 = 누른줄 && (그줄(누른줄) || {dataset: {}}).dataset.edit === '1';
    if (편집중() && 누른줄 && 고칠수있는줄) {
      띄운다(누른줄,
        '<div class="poprow">편집을 저장하거나 끈 뒤에 엽니다 — 지금 열면 고치던 칸이 사라집니다.</div>',
        'longpop');
      return;
    }
    if (긴) { 긴팝(긴); return; }
    if (t.closest('.popsave') && 주인 && 주인.classList.contains('longcell')) {
      긴칸저장(주인); return;
    }
    var 칩 = t.closest('.rcptchip');
    if (칩) { 영수증팝(칩); return; }
    var 첨부 = t.closest('.rcptadd');
    if (첨부) { 올리기팝(첨부, 첨부.dataset.exp, false); return; }
    var 더 = t.closest('.rcptmore');
    if (더) { 올리기팝(더, 더.dataset.exp, true); return; }

    /* **계좌는 눌러서도 연다** (2026-09-27 사람이 정함) — 손가락에는 호버가
       없어 올림으로만 열면 **그 기기에서 계좌를 볼 길이 통째로 없다**
       (7-4 의 「휴대폰은 눌러서 열고 다른 곳을 눌러 닫습니다」). 올림으로
       여는 길은 그대로 두고 **둘 다** 된다.

       **두 번 뜨지 않는다** — 마우스로 누르면 바깥 누름 판정이 먼저 그 팝업을
       닫고 이 줄이 같은 자리에 다시 그린다. 손가락은 그 판정이 뜨기 전에
       지나가므로 올림이 먼저 열고, 이 줄의 `띄운다` 가 **같은 주인이면
       그 팝업을 그대로 돌려준다.**

       **편집 중 막기는 여기 해당 없다** — 막기의 축은 「저장이 일어날 수
       있나」 이고(2026-09-26 두 번째 검토 [10]), **계좌 팝업에는 저장도
       화면 다시 읽기도 없어 버릴 편집이 애초에 없다.** 그래서 위의
       `누른줄` 에 계좌를 안 넣는다.

       **「편집을 켜면 이 단추가 입력칸으로 바뀌어 사라진다」 를 까닭으로
       쓰지 않는다** — 바뀌는 것은 `data-edit="1"` 인 줄뿐이라, 계좌가 적힌
       **취소된 줄**에서는 그대로 남는다(2026-09-27 커밋 전 검토 [B]).
       없는 조건에 기대면 그 줄을 본 다음 사람이 「글이 틀렸으니 막기를
       넓히자」 로 간다. */
    var 계좌 = t.closest('.payer.acct');
    if (계좌) { 계좌팝(계좌); return; }

    var 올림 = t.closest('.rupload');
    if (올림 && 팝) {
      var fd = new FormData();
      var f = 팝.querySelector('.rfile');
      if (f && f.files && f.files[0]) fd.append('receipt', f.files[0]);
      fd.append('memo', (팝.querySelector('.rmemo') || {}).value || '');
      fd.append('original_no', (팝.querySelector('.rorig') || {}).value || '');
      보낸다('/expenses/' + 올림.dataset.exp + '/receipts', fd, 올림);
      return;
    }
    var 잇기 = t.closest('.rlink');
    if (잇기 && 팝) {
      var no = (팝.querySelector('.rno') || {}).value || '';
      if (!no.trim()) { 말한다('이을 영수증 번호를 적어 주세요.'); return; }
      var b = new URLSearchParams(); b.set('number', no.trim());
      보낸다('/expenses/' + 잇기.dataset.exp + '/receipts/link', b, 잇기);
      return;
    }
    var 원본 = t.closest('.rorigsave');
    if (원본 && 팝) {
      var ob = new URLSearchParams();
      ob.set('original_no', (팝.querySelector('.rorig') || {}).value || '');
      보낸다('/expenses/' + 원본.dataset.exp + '/receipts/' + 원본.dataset.rcpt + '/original',
             ob, 원본);
      return;
    }
    var 삭제 = t.closest('.rcptdel');
    if (삭제) {
      /* **한 번 되묻는다** (2026-09-26 검토 [O]) — 되돌릴 수는 있지만 번호를
         기억해야 하고, 말이 「삭제」 라 더 그렇다. 옛 화면도 되물었다 */
      if (!confirm('영수증 ' + (주인 ? 주인.dataset.no : '') + '번을 이 지출에서 뗄까요? 영수증은 남습니다.')) return;
      보낸다('/expenses/' + 삭제.dataset.exp + '/receipts/' + 삭제.dataset.rcpt + '/detach',
             new URLSearchParams(), 삭제);
      return;
    }
  });
})();
