"""회차 날짜를 옮기면 업무가 따라오는가 · 급을 올린 자리를 페이지 전체에서 (2026-09-12).

| 잰 것 | 어디 |
|---|---|
| 가 | 개회일을 옮기면 업무가 **D-주차를 지킨 채** 따라온다 — 안 따라오는 종류도 |
| — | 손으로 옮긴 자리와 부딪힘은 `tests/test_stage39.py` 가 잽니다(여기가 아닙니다) |
| 나 | `test_ts_02c` 의 범위 — `tests/test_typescale.py` 가 잽니다(여기가 아닙니다) |

**합성 자료만 씁니다** — 운영 DB 는 시험이 열지 않습니다. 운영에서 센 값은
읽기 전용으로 따로 읽었고 보고에 있습니다.

각 독스트링에 **그 줄이 실제로 무엇을 보는지** 적습니다 — 막혀야 할 것이
막히는가 · 막히면 안 되는 것이 통과하는가 · 검사가 볼 것을 보고 있는가(11-3).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models import Department, Retreat, TaskLibrary, TaskRun
from tests.conftest import app_session

첫개회 = dt.date(2027, 8, 20)
옮긴개회 = dt.date(2027, 9, 17)     # 넉 주 뒤 · 같은 금요일


def _d1주(개회: dt.date) -> dt.date:
    """개회일 직전 일요일 (6-4). 개회일이 일요일이면 그날."""
    return 개회 - dt.timedelta(days=(개회.weekday() + 1) % 7)


def _그주(개회: dt.date, d_week: int) -> dt.date:
    return _d1주(개회) - dt.timedelta(days=(d_week - 1) * 7)


@pytest.fixture
def 회차(admin_client):
    """회차 하나 + 업무 다섯 — 켠 것 셋, 뺀 것 하나, D-주차가 빈 것 하나.

    **라이브러리에 상대 위치를 제대로 넣습니다**(`default_offset_days` ·
    `default_span_days`). 날짜를 다시 세는 것이 라이브러리이므로(14장),
    거기가 비면 잰 값이 「그 회차의 사정」 이 아니라 「빈 명세」 가 됩니다.
    """
    with app_session() as db:
        r = Retreat(name="2027 여름수련회", start_date=첫개회,
                    end_date=첫개회 + dt.timedelta(days=2))
        db.add(r)
        db.flush()
        db.add(Department(retreat_id=r.id, key="seongyo", name="3 선교사회", sort_order=0))
        db.flush()
        # (D-주차, 켤까, 그 주 일요일에서 며칠, 며칠짜리)
        차림 = [(13, True, 3, 3), (8, True, 0, 6), (2, True, 5, 1),
               (5, False, 0, 0), (None, True, 0, 0)]
        for i, (dw, inc, 오프셋, 기간) in enumerate(차림):
            lib = TaskLibrary(title=f"업무 {i}", kind="main", date_anchor="week",
                              default_d_week=dw, default_offset_days=오프셋,
                              default_span_days=기간)
            db.add(lib)
            db.flush()
            시작 = (_그주(첫개회, dw) + dt.timedelta(days=오프셋)) if dw else None
            db.add(TaskRun(library_id=lib.id, retreat_id=r.id, included=inc,
                           run_no=i + 1, d_week=dw,
                           start_date=시작,
                           end_date=(시작 + dt.timedelta(days=기간)) if 시작 else None))
        db.commit()
        return r.id


def _줄들(rid: int):
    with app_session() as db:
        return {r.run_no: (r.d_week, r.start_date, r.end_date, r.included)
                for r in db.scalars(select(TaskRun).where(TaskRun.retreat_id == rid)).all()}


def _날짜를옮긴다(client, rid: int, 개회: dt.date):
    return client.post(f"/retreats/{rid}/update", data={
        "name": "2027 여름수련회",
        "start_date": 개회.isoformat(),
        "end_date": (개회 + dt.timedelta(days=2)).isoformat(),
        "meal_subsidy_per_person": 8000,
    }, follow_redirects=False)


def test37_a01_개회일을_옮기면_업무가_D주차를_지킨_채_따라온다(admin_client, 회차):
    """가) **둘을 같은 판에서 봅니다** — 따라오는 것과 안 따라오는 것.

    사람이 2026-09-12 에 운영에서 이 일을 했습니다(2027 개회일을 8월 20일로).
    그 결과를 읽어서 확인했고(보고 1장), 여기서는 **같은 길이 합성 자료에서
    어떻게 도는지**를 잽니다.

    봅니다 — ① 옮기기 전 D-주차가 지켜져 있었나(안 그러면 뒤가 뜻이 없습니다)
    ② 옮긴 뒤에도 **각자의 D-주차 주 안에** 있나 ③ **그 주 안의 며칠째가
    그대로인가**(14장 — 개회일 요일이 달라져도 업무의 자리는 유지되어야
    합니다) ④ **며칠짜리인지가 그대로인가**(옮기는 것이지 늘리는 것이 아닙니다)
    ⑤ **뺀 업무는 아예 안 건드려지는가** ⑥ 회차 상세가 열리는가.

    **⑦ 은 날짜가 빈 채 켜져 있는 업무입니다.** 전에는
    `d_week or FIRST_D_WEEK` 로 떨어져 **없던 날짜를 얻었는데**(봐둘것 AW-c),
    2026-09-12 판이 그것을 닫아 **빈 채로 남습니다.** 그 판 전에는 이 줄이
    「기본 D-주차 자리로 갔나」 를 쟀고, 고친 뒤 실제로 빨개져서 이 줄이
    무는 것을 봤습니다. 운영에서는 그때도 안 밟혔습니다(날짜 없는 여섯이
    전부 뺀 것이라 ⑤ 로 걸러집니다). 자세한 것은 `tests/test_stage39.py`.
    """
    앞 = _줄들(회차)
    for no, (dw, sd, _, _) in 앞.items():
        if dw and sd:
            assert 0 <= (sd - _그주(첫개회, dw)).days <= 6, f"① run {no} 이 처음부터 어긋났다"

    답 = _날짜를옮긴다(admin_client, 회차, 옮긴개회)
    assert 답.status_code == 303

    뒤 = _줄들(회차)
    옮겨진, 안건드림, 빈채남음 = 0, 0, 0
    for no, (dw, sd, ed, inc) in 뒤.items():
        앞dw, 앞시작, 앞끝, 앞inc = 앞[no]
        if not 앞inc:                      # ⑤ 뺀 것 — reschedule 이 건너뛴다
            assert (sd, ed) == (앞시작, 앞끝), f"⑤ run {no} 이 건드려졌다"
            안건드림 += 1
            continue
        if 앞시작 is None:                 # ⑦ 날짜가 빈 채 켜진 것
            assert sd is None and ed is None, \
                f"⑦ run {no} 이 없던 날짜를 얻었다 (봐둘것 AW-c)"
            빈채남음 += 1
            continue
        assert sd is not None, f"run {no} 의 날짜가 사라졌다"
        assert 0 <= (sd - _그주(옮긴개회, dw)).days <= 6, f"② run {no} 이 그 주를 벗어났다"
        assert (sd - _그주(옮긴개회, dw)).days == (앞시작 - _그주(첫개회, 앞dw)).days, \
            f"③ run {no} 의 그 주 안 자리가 바뀌었다"
        assert (ed - sd) == (앞끝 - 앞시작), f"④ run {no} 의 기간이 바뀌었다"
        assert sd != 앞시작, f"run {no} 이 안 움직였다"
        옮겨진 += 1

    assert (옮겨진, 안건드림, 빈채남음) == (3, 1, 1), \
        f"셋으로 갈려야 한다: 옮겨진 {옮겨진} · 안 건드림 {안건드림} · 빈 채 남음 {빈채남음}"

    assert admin_client.get(f"/settings/retreats/{회차}").status_code == 200, \
        "⑥ 회차 상세가 안 열린다"


# `test37_a03` 은 없앴습니다 — 「손으로 옮긴 날짜는 개회일이 바뀌면 되돌아간다」
# 를 재던 줄인데, **2026-09-12 판이 그 고장을 닫았습니다**(봐둘것 AW-b).
# 그 줄이 실제로 재던 것 — DB 에 직접 쓴 날짜는 「옮김」 이 아니라서 다시
# 셈해진다 — 은 `tests/test_stage39.py` 의 `test39_f02` 가 **그 이름으로**
# 잽니다. 같은 것을 두 곳에서 재면 한쪽만 고쳐집니다.
