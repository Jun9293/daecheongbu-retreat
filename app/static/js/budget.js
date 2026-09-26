/* 예산 (CLAUDE.md 7-3) — 보는 판은 서버가 그리고, 「전체 편집」 은 **한 모델**
 * 에서 같은 표를 다시 그린다.
 *
 * 왜 다시 그리나 — 줄을 옮기면 구분·항목의 병합(rowspan)이 통째로 달라진다.
 * 서버가 그린 칸을 손으로 쪼개고 붙이는 것보다 모델 하나에서 다시 그리는 쪽이
 * 갈릴 자리가 적다(4-13 이 달 격자를 통째로 갈아 끼우는 것과 같은 판단).
 *
 * 저장은 **한 번에 전부**다 — 줄마다 저장하면 절반만 들어간 표가 생긴다.
 * 실패하면 **편집 상태를 그대로 두고 그 자리에 까닭을 적는다**: 조용히
 * 삼키면 고친 줄 알고 넘어간다(5-0 과 같은 자리).
 */
(function () {
  'use strict';

  var 표 = document.getElementById('budtbl');
  var 씨앗 = document.getElementById('bud-rows');
  if (!표 || !씨앗) return;

  var 원본 = JSON.parse(씨앗.textContent || '[]');
  var 줄들 = null;                 // 편집 중인 모델 (null 이면 보는 판)
  var 뺀것 = [];
  var 켬 = false;

  var 단추 = document.getElementById('budedit');
  var 띠 = document.getElementById('budbar');
  var 말 = document.getElementById('budmsg');
  var 저장 = document.getElementById('budsave');
  var 되돌림 = document.getElementById('budcancel');
  var 줄추가 = document.getElementById('budadd');
  var 보던판 = 표.querySelector('tbody').innerHTML;

  function 콤마(v) {
    if (v === null || v === undefined || v === '') return '';
    var n = parseInt(String(v).replace(/[^0-9-]/g, ''), 10);
    return isNaN(n) ? '' : n.toLocaleString('ko-KR');
  }
  function 수(v) {
    var t = String(v === null || v === undefined ? '' : v).replace(/[^0-9-]/g, '');
    return t === '' ? null : parseInt(t, 10);
  }
  function esc(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* 예산금액 = 단가 × 명수 × 횟수, 셋이 비면 직접 입력값 (7-3).
     **셈은 저장할 때 서버가 다시 한다** — 여기 것은 미리보기다. */
  function 예산금액(줄) {
    if (줄.unit_price !== null && 줄.headcount !== null && 줄.times !== null) {
      return 줄.unit_price * 줄.headcount * 줄.times;
    }
    return 줄.planned_amount || 0;
  }

  /* 같은 구분 · 같은 항목이 **이어진 줄**만 묶는다 — 서버(`GroupSummary.items`)와
     같은 규칙이다. 떨어져 있는 같은 이름을 붙이면 사람이 놓은 자리가 바뀐다. */
  function 묶는다(줄들) {
    var 구분들 = [];
    줄들.forEach(function (줄, i) {
      var g = 구분들[구분들.length - 1];
      if (!g || g.name !== 줄.level1) {
        g = {name: 줄.level1, items: []};
        구분들.push(g);
      }
      var it = g.items[g.items.length - 1];
      if (!it || it.name !== 줄.level2) {
        it = {name: 줄.level2, rows: []};
        g.items.push(it);
      }
      it.rows.push({줄: 줄, i: i});
    });
    return 구분들;
  }

  function 칸(줄, 이름, cls) {
    return '<input class="bi ' + (cls || '') + '" data-f="' + 이름 + '" value="' +
      esc(줄[이름] === null || 줄[이름] === undefined ? '' : 줄[이름]) + '">';
  }
  function 돈칸(줄, 이름) {
    return '<input class="bi r mono" data-f="' + 이름 + '" inputmode="numeric" value="' +
      콤마(줄[이름]) + '">';
  }

  function 그린다() {
    var 구분들 = 묶는다(줄들);
    var html = '';
    구분들.forEach(function (g) {
      var 줄수 = g.items.reduce(function (a, it) { return a + it.rows.length; }, 0);
      var 예산합 = 0, 결산합 = 0;
      g.items.forEach(function (it) {
        it.rows.forEach(function (r) { 예산합 += 예산금액(r.줄); 결산합 += r.줄.spent || 0; });
      });
      g.items.forEach(function (it, ii) {
        it.rows.forEach(function (r, ri) {
          var 줄 = r.줄;
          html += '<tr data-i="' + r.i + '">';
          if (ii === 0 && ri === 0) {
            html += '<td class="l1" rowspan="' + 줄수 + '">' +
              '<input class="bi" data-f="level1" data-all="1" value="' + esc(줄.level1) + '"></td>';
          }
          if (ri === 0) {
            /* 핸들은 **편집 상태에서만** 있다 — 보는 판에는 아예 안 그린다 */
            html += '<td class="l2" rowspan="' + it.rows.length + '">' +
              '<span class="grip" draggable="true" data-grip="item" title="항목 통째로 옮기기">⠿</span>' +
              '<input class="bi" data-f="level2" data-all="1" value="' + esc(줄.level2) + '"></td>';
          }
          html += '<td class="l3"><span class="grip" draggable="true" data-grip="row" title="세부항목 옮기기">⠿</span>' +
            칸(줄, 'level3') + '</td>';
          html += '<td class="r">' + 돈칸(줄, 'unit_price') + '</td>';
          html += '<td class="r">' + 돈칸(줄, 'headcount') + '</td>';
          html += '<td class="r">' + 돈칸(줄, 'times') + '</td>';
          html += '<td class="r">' + 돈칸(줄, 'planned_amount') + '</td>';
          html += '<td class="r mono dim">–</td>';
          html += '<td class="r mono">' + 콤마(줄.spent || 0) + '</td>';
          html += '<td class="r mono dim">–</td>';
          html += '<td class="r mono">' + 콤마(예산금액(줄) - (줄.spent || 0)) + '</td>';
          html += '<td class="note">' + 칸(줄, 'note') +
            '<button type="button" class="sbtn budout" title="이 줄을 취소한다 — 행은 아래에 남는다">취소</button></td>';
          html += '</tr>';
        });
      });
      html += '<tr class="subtot"><td colspan="6" class="r">소계</td>' +
        '<td class="r mono">' + 콤마(예산합) + '</td><td class="r mono dim">–</td>' +
        '<td class="r mono">' + 콤마(결산합) + '</td><td class="r mono dim">–</td>' +
        '<td class="r mono">' + 콤마(예산합 - 결산합) + '</td><td></td></tr>';
    });
    표.querySelector('tbody').innerHTML = html ||
      '<tr><td colspan="12" class="dim">줄이 없습니다 — 「+ 줄 추가」 로 시작합니다.</td></tr>';
  }

  /* 화면의 값을 모델로 걷는다 — 다시 그리기 전에 부른다.
     **안 걷고 다시 그리면 방금 친 글자가 사라진다.** */
  function 걷는다() {
    표.querySelectorAll('tbody tr[data-i]').forEach(function (tr) {
      var 줄 = 줄들[parseInt(tr.dataset.i, 10)];
      if (!줄) return;
      tr.querySelectorAll('input.bi').forEach(function (el) {
        var f = el.dataset.f;
        if (f === 'level1' || f === 'level2' || f === 'level3' || f === 'note') {
          줄[f] = el.value;
        } else {
          줄[f] = 수(el.value);
        }
      });
    });
    /* 병합된 칸은 그 묶음의 **모든 줄**에 같은 값이다 — 한 칸을 고치면 묶음이
       통째로 바뀐다. 안 그러면 고친 이름이 첫 줄에만 붙어 묶음이 쪼개진다 */
    var 구분들 = 묶는다(줄들);
    구분들.forEach(function (g) {
      g.items.forEach(function (it) {
        var 첫 = it.rows[0].줄;
        it.rows.forEach(function (r) { r.줄.level1 = 첫.level1; r.줄.level2 = 첫.level2; });
      });
    });
  }

  function 편집켜기(on) {
    켬 = on;
    표.classList.toggle('editing', on);
    if (띠) 띠.hidden = !on;
    if (단추) {
      단추.textContent = on ? '편집 끄기' : '전체 편집';
      단추.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    if (on) {
      줄들 = 원본.map(function (r) { return Object.assign({}, r); });
      뺀것 = [];
      그린다();
    } else {
      표.querySelector('tbody').innerHTML = 보던판;
      줄들 = null;
      묶기();
    }
    if (말) 말.textContent = '';
  }

  if (단추) 단추.addEventListener('click', function () { if (켬) 걷는다(); 편집켜기(!켬); });
  if (되돌림) 되돌림.addEventListener('click', function () { 편집켜기(false); });

  if (줄추가) 줄추가.addEventListener('click', function () {
    걷는다();
    var 끝 = 줄들[줄들.length - 1];
    줄들.push({
      id: null, level1: 끝 ? 끝.level1 : '', level2: 끝 ? 끝.level2 : '', level3: '',
      unit_price: null, headcount: null, times: null, planned_amount: 0, note: '', spent: 0
    });
    그린다();
  });

  표.addEventListener('click', function (e) {
    var out = e.target.closest('.budout');
    if (out) {
      걷는다();
      var tr = out.closest('tr[data-i]');
      var 줄 = 줄들[parseInt(tr.dataset.i, 10)];
      if (줄 && 줄.id) 뺀것.push(줄.id);
      줄들.splice(줄들.indexOf(줄), 1);
      그린다();
      return;
    }
    var back = e.target.closest('.budback');
    if (back) 되살린다(back);
  });

  /* 뺀 줄을 되살린다 — 서버는 같은 토글 하나다(7-3). 실패하면 말한다 */
  function 되살린다(btn) {
    btn.disabled = true;
    fetch('/budget/categories/' + btn.dataset.cat + '/cancel', {
      method: 'POST', headers: {'X-Requested-With': 'fetch'}
    }).then(function (r) {
      if (!r.ok) throw new Error('되살리지 못했습니다');
      location.reload();
    }).catch(function (err) {
      btn.disabled = false;
      if (말) 말.textContent = String(err.message || err);
    });
  }

  /* ── 끌어 옮기기 — 핸들에서만 시작한다 (편집 상태에서만 그려진다) ── */
  var 끄는것 = null;
  표.addEventListener('dragstart', function (e) {
    var grip = e.target.closest('[data-grip]');
    if (!grip || !켬) return;
    걷는다();
    var tr = grip.closest('tr[data-i]');
    var i = parseInt(tr.dataset.i, 10);
    if (grip.dataset.grip === 'item') {
      // 항목 통째 — 같은 구분·같은 항목으로 **이어진** 줄 전부
      var 줄 = 줄들[i], 처음 = i, 끝 = i;
      while (처음 > 0 && 줄들[처음 - 1].level1 === 줄.level1 && 줄들[처음 - 1].level2 === 줄.level2) 처음--;
      while (끝 + 1 < 줄들.length && 줄들[끝 + 1].level1 === 줄.level1 && 줄들[끝 + 1].level2 === 줄.level2) 끝++;
      끄는것 = {from: 처음, count: 끝 - 처음 + 1, 묶음: true};
    } else {
      끄는것 = {from: i, count: 1, 묶음: false};
    }
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', String(i)); } catch (x) {}
  });

  표.addEventListener('dragover', function (e) {
    if (!끄는것) return;
    var tr = e.target.closest('tr[data-i]');
    if (!tr) return;
    e.preventDefault();
    var r = tr.getBoundingClientRect();
    tr.classList.toggle('dropafter', e.clientY > r.top + r.height / 2);
    tr.classList.toggle('dropbefore', e.clientY <= r.top + r.height / 2);
  });
  표.addEventListener('dragleave', function (e) {
    var tr = e.target.closest('tr[data-i]');
    if (tr) tr.classList.remove('dropafter', 'dropbefore');
  });

  표.addEventListener('drop', function (e) {
    if (!끄는것) return;
    var tr = e.target.closest('tr[data-i]');
    if (!tr) { 끄는것 = null; return; }
    e.preventDefault();
    var 아래 = tr.classList.contains('dropafter');
    tr.classList.remove('dropafter', 'dropbefore');
    var 목표 = parseInt(tr.dataset.i, 10) + (아래 ? 1 : 0);
    var 옮길 = 줄들.splice(끄는것.from, 끄는것.count);
    if (목표 > 끄는것.from) 목표 -= 끄는것.count;
    목표 = Math.max(0, Math.min(목표, 줄들.length));
    /* **세부항목 하나를 옮기면 그 자리의 구분·항목을 따라간다.** 안 그러면
       화면에서는 그 묶음 안에 있는데 이름만 옛 묶음이라, 저장하고 새로
       고치는 순간 제자리로 돌아간다 */
    if (!끄는것.묶음) {
      var 이웃 = 줄들[목표 - 1] || 줄들[목표];
      if (이웃) { 옮길[0].level1 = 이웃.level1; 옮길[0].level2 = 이웃.level2; }
    }
    줄들.splice.apply(줄들, [목표, 0].concat(옮길));
    끄는것 = null;
    그린다();
  });

  /* 저장 — **한 번에 전부**. 두 번 눌러도 한 번만 간다(누르는 동안 잠근다) */
  if (저장) 저장.addEventListener('click', function () {
    걷는다();
    저장.disabled = true;
    if (말) 말.textContent = '저장하는 중…';
    var 몸 = {
      rows: 줄들.map(function (줄) {
        return {
          id: 줄.id, level1: 줄.level1, level2: 줄.level2, level3: 줄.level3,
          unit_price: 줄.unit_price, headcount: 줄.headcount, times: 줄.times,
          planned_amount: 예산금액(줄), note: 줄.note
        };
      }),
      removed: 뺀것
    };
    fetch('/budget/bulk', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(몸)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || ('저장하지 못했습니다 (' + r.status + ')'));
        return j;
      });
    }).then(function () {
      location.reload();
    }).catch(function (err) {
      /* **편집 상태를 그대로 둔다** — 여기서 화면을 되돌리면 방금 친 것이 사라진다 */
      저장.disabled = false;
      if (말) 말.textContent = String(err.message || err);
    });
  });

  /* 편집 중에도 금액은 천 단위 콤마 (7-3 · 2026-09-26) */
  표.addEventListener('input', function (e) {
    var el = e.target;
    if (!el.classList || !el.classList.contains('mono') || !el.dataset.f) return;
    var 끝 = el.selectionStart === el.value.length;
    var v = 콤마(el.value);
    if (v !== el.value) {
      el.value = v;
      if (끝) el.setSelectionRange(v.length, v.length);
    }
  });

  /* 보는 판의 병합 칸에 세로 가운데 정렬 — CSS 가 하지만, 다시 그린 뒤에도
     같은 클래스를 쓰므로 여기서 할 일은 없다. 자리만 남겨 둔다 */
  function 묶기() {}
})();
