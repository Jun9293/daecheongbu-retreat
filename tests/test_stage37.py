"""회차 날짜를 옮기면 업무가 따라오는가 · 급을 올린 자리를 페이지 전체에서 (2026-09-12).

| 잰 것 | 어디 |
|---|---|
| 가 | 개회일을 옮기면 업무가 **D-주차를 지킨 채** 따라온다 — 안 따라오는 종류도 |
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

    **⑦ 은 안 따라오는 쪽이 아니라 「뜻밖에 따라오는 쪽」 입니다** —
    D-주차가 빈 채 켜져 있는 업무는 `dweek.resolve_dates` 가
    `d_week or FIRST_D_WEEK` 로 떨어뜨려 **없던 날짜를 얻습니다.**
    운영에서는 안 밟힙니다(날짜 없는 여섯이 전부 뺀 것이라 ⑤ 로 걸러집니다).
    고치지 않고 `docs/봐둘것.md` 에 적었습니다.
    """
    from app.domain.dweek import FIRST_D_WEEK
    앞 = _줄들(회차)
    for no, (dw, sd, _, _) in 앞.items():
        if dw and sd:
            assert 0 <= (sd - _그주(첫개회, dw)).days <= 6, f"① run {no} 이 처음부터 어긋났다"

    답 = _날짜를옮긴다(admin_client, 회차, 옮긴개회)
    assert 답.status_code == 303

    뒤 = _줄들(회차)
    옮겨진, 안건드림, 날짜를얻음 = 0, 0, 0
    for no, (dw, sd, ed, inc) in 뒤.items():
        앞dw, 앞시작, 앞끝, 앞inc = 앞[no]
        if not 앞inc:                      # ⑤ 뺀 것 — reschedule 이 건너뛴다
            assert (sd, ed) == (앞시작, 앞끝), f"⑤ run {no} 이 건드려졌다"
            안건드림 += 1
            continue
        if 앞시작 is None:                 # ⑦ D-주차가 빈 채 켜진 것
            assert sd == _그주(옮긴개회, FIRST_D_WEEK), \
                f"⑦ run {no} 이 기본 D-주차 자리로 안 갔다 — 이 시험이 낡았다"
            날짜를얻음 += 1
            continue
        assert sd is not None, f"run {no} 의 날짜가 사라졌다"
        assert 0 <= (sd - _그주(옮긴개회, dw)).days <= 6, f"② run {no} 이 그 주를 벗어났다"
        assert (sd - _그주(옮긴개회, dw)).days == (앞시작 - _그주(첫개회, 앞dw)).days, \
            f"③ run {no} 의 그 주 안 자리가 바뀌었다"
        assert (ed - sd) == (앞끝 - 앞시작), f"④ run {no} 의 기간이 바뀌었다"
        assert sd != 앞시작, f"run {no} 이 안 움직였다"
        옮겨진 += 1

    assert (옮겨진, 안건드림, 날짜를얻음) == (3, 1, 1), \
        f"셋으로 갈려야 한다: 옮겨진 {옮겨진} · 안 건드림 {안건드림} · 날짜 얻음 {날짜를얻음}"

    assert admin_client.get(f"/settings/retreats/{회차}").status_code == 200, \
        "⑥ 회차 상세가 안 열린다"


def test37_a03_손으로_옮긴_날짜는_개회일이_바뀌면_되돌아간다(admin_client, 회차):
    """가) 곁가지 — **「옮긴다」 가 아니라 「라이브러리에서 다시 센다」 입니다.**

    `library.reschedule` 은 run 의 옛 날짜를 밀어 주는 것이 아니라
    **라이브러리의 상대 위치로 다시 셉니다**(14장 · 6-4). 그래서 보드에서
    바를 끌어 옮겨 둔 날짜(4-6)는 **개회일이 바뀌는 순간 기본값으로
    돌아갑니다** — 이 시험을 쓰다가 알게 된 것이고, 고치지 않고
    `docs/봐둘것.md` 에 적었습니다.

    봅니다 — ① 손으로 옮긴 값이 실제로 저장되는가(안 그러면 뒤가 무의미)
    ② 개회일을 바꾸면 **그 값이 라이브러리 기본 자리로 돌아가는가**
    ③ 그 자리가 D-주차 규칙과 맞는가(되돌아간 곳이 아무 데나가 아님)
    ④ **뺀 업무는 이때도 안 건드려지는가.**
    """
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 2)).first()
        손으로 = run.start_date + dt.timedelta(days=2)
        run.start_date = 손으로
        run.end_date = 손으로 + dt.timedelta(days=6)
        db.commit()
    assert _줄들(회차)[2][1] == 손으로, "① 손으로 옮긴 값이 안 저장된다"

    뺀것앞 = _줄들(회차)[4]
    _날짜를옮긴다(admin_client, 회차, 옮긴개회)
    뒤 = _줄들(회차)

    dw = 뒤[2][0]
    기본자리 = _그주(옮긴개회, dw)          # 그 라이브러리의 오프셋은 0 이다
    assert 뒤[2][1] == 기본자리, "② 손으로 옮긴 자리가 남았다 — 이 시험이 낡았다"
    assert 0 <= (뒤[2][1] - _그주(옮긴개회, dw)).days <= 6, "③ 엉뚱한 주로 갔다"
    assert 뒤[4] == 뺀것앞, "④ 뺀 업무가 건드려졌다"


def test37_a02_날짜를_안_바꾸면_업무도_안_움직인다(admin_client, 회차):
    """가) 반대쪽 — **막히면 안 되는 것이 통과하는가**의 짝입니다.

    `a01` 이 「옮기면 따라온다」 를 재므로, 이 줄은 **「안 옮기면 안 따라온다」**
    를 잽니다. 둘이 있어야 「늘 다시 계산한다」 와 구별됩니다 — 늘 계산하면
    사람이 이름만 고쳐도 날짜가 흔들립니다.

    봅니다 — ① 이름만 바꾼 저장이 되는가 ② **업무 날짜가 한 건도 안 바뀌는가**
    ③ 회차 이름은 실제로 바뀌었나(① 이 「아무것도 안 했다」 가 아님).
    """
    앞 = _줄들(회차)
    답 = admin_client.post(f"/retreats/{회차}/update", data={
        "name": "2027 여름수련회 (이름만 고침)",
        "start_date": 첫개회.isoformat(),
        "end_date": (첫개회 + dt.timedelta(days=2)).isoformat(),
        "meal_subsidy_per_person": 8000,
    }, follow_redirects=False)
    assert 답.status_code == 303, "① 저장이 안 된다"

    assert _줄들(회차) == 앞, "② 날짜를 안 바꿨는데 업무가 움직였다"
    with app_session() as db:
        assert db.get(Retreat, 회차).name.endswith("(이름만 고침)"), "③ 이름이 안 바뀌었다"
