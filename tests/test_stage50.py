"""못 이은 지출을 화면에서 잇는다 (2026-09-15 · 재정 짝 표 30 건 · 봐둘것 BB-h).

차례 5 의 「고치기」(`update_expense`)가 **예산 항목 없는 지출에 항목을 골라 저장하는 길**로 실제로 도는지 잰다.
화면을 그리는 것(목록의 「예산 항목 미지정」 묶음 · 고치기 폼의 예산 항목 선택지)부터 저장까지 같은 앱에서 잰다.
**이 창은 도는 서버에 로그인하지 않는다**(CLAUDE.md 11-2) — 그래서 개발 서버 대신 앱을 그 자리에서 만드는 시험이다.

값은 지어낸 것이다.
"""

from __future__ import annotations

import datetime as dt
import html
import re

from sqlalchemy import select

from app import models
from tests.conftest import app_session
from tests.test_stage47 import _고침, 판  # noqa: F401 — 판 은 fixture


def _시트에서_온_미지정(판, 부서=True):
    """들여오기가 못 이은 줄과 같은 꼴 — 예산 항목 없음 · 시트 글자는 구분·항목·세부1 에 남음 · 세부2 빔."""
    with app_session() as db:
        e = models.ExpenseEntry(retreat_id=판["retreat"], budget_category_id=None, amount=23_450, subsidy_amount=23_450, expense_date=dt.date(2026, 8, 1),
                                level1="지어낸구분", level2="지어낸항목", level3a="지어낸세부",
                                department_id=판["dept"] if 부서 else None, payer_name="가명")
        db.add(e)
        db.commit()
        return e.id


def test50_a01_미지정_묶음과_고치기_폼에_예산_항목_선택지가_뜬다(admin_client, 판):
    eid = _시트에서_온_미지정(판)
    page = admin_client.get(f"/expenses?retreat_id={판['retreat']}").text
    assert "예산 항목 미지정" in page, "못 이은 지출이 모이는 묶음이 안 보인다"
    폼 = re.search(rf'<form method="post" action="/expenses/{eid}/update".*?</form>', page, re.S)
    assert 폼, "그 지출의 고치기 폼이 안 그려졌다"
    선택 = re.search(r'<select name="budget_category_id".*?</select>', 폼.group(0), re.S).group(0)
    assert f'<option value="{판["c1"]}"' in 선택 and f'<option value="{판["c2"]}"' in 선택
    assert " selected" not in 선택, "미지정 지출인데 어떤 항목이 미리 골라져 있다"
    # 금액 칸이 들여온 금액을 그대로 받는가 — step="10" 이면 10원 단위가 아닌 줄은 브라우저가 저장을 막는다(서버 시험에 안 보인다)
    금액칸 = re.search(r'<input name="amount"[^>]*>', 폼.group(0)).group(0)
    step = re.search(r'step="(\d+)"', 금액칸)
    assert step is None or 23_451 % int(step.group(1)) == 0, "고치기 금액 칸이 10원 단위가 아닌 금액을 막는다"
    # 목록의 그 줄 제목은 세부항목-2 가 비어 「미지정」 — 시트 글자(구분·항목·세부1)는 화면에 안 보인다(안내문이 짝 표를 쓰게 한 까닭)
    assert "지어낸구분" not in page and "지어낸세부" not in page


def test50_b01_항목을_골라_저장하면_이어지고_부서는_그대로(admin_client, 판):
    eid = _시트에서_온_미지정(판)
    r = _고침(admin_client, 판, eid, budget_category_id=판["c2"])
    assert r.status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        c2 = db.get(models.BudgetCategory, 판["c2"])
        assert e.budget_category_id == 판["c2"], "항목을 골라 저장했는데 안 이어졌다"
        assert e.department_id == 판["dept"], "예산 항목을 바꿨더니 부서가 바뀌었다"
        # 시트에서 온 구분·항목·세부1 글자는 새 항목의 글자로 덮인다 — 되돌리는 길은 활동 기록이 아니라 시트·사본(안내문에 굵게)
        assert (e.level1, e.level2, e.level3a) == (c2.level1, c2.level2, c2.level3)
        assert e.amount == 23_450 and e.subsidy_amount == 23_450, "금액·지원금액은 안 바뀐다"
        log = db.scalars(select(models.ActivityLog).where(models.ActivityLog.action == "지출_수정")
                         .order_by(models.ActivityLog.id.desc())).first()
        assert log is not None and "budget_category_id" in log.after_value
        assert "level1" not in log.after_value, "덮인 시트 글자는 기록에 안 남는다 — 안내문이 말하는 그대로인지"
    # 이어진 뒤 목록에서 그 항목 묶음 아래로 간다
    page = admin_client.get(f"/expenses?retreat_id={판['retreat']}").text
    assert "예산 항목 미지정" not in page, "판의 미지정 지출은 이 하나뿐이라 묶음이 사라져야 한다"
    머리들 = re.findall(r'<div class="grouphead">\s*<b>(.*?)</b>', page)
    assert html.escape(c2.display_name) in 머리들


def test50_b02_부서_없는_지출도_총무팀이_잇는다(admin_client, 판):
    """운영의 못 이은 30 건은 부서가 안 붙어 있다(2026-09-15 운영 셈) — 총무팀 문을 지나는지."""
    eid = _시트에서_온_미지정(판, 부서=False)
    assert _고침(admin_client, 판, eid, budget_category_id=판["c1"]).status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert e.budget_category_id == 판["c1"] and e.department_id is None
