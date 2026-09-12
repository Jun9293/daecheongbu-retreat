"""손으로 옮긴 자리를 개회일이 바뀌어도 살린다 (6-4 · 봐둘것 AW-b · AW-c).

| 잰 것 | 어디 |
|---|---|
| 가 | 옮긴 업무는 **같은 간격**을 지키고 안 옮긴 업무는 다시 셈해진다 |
| 나 | 켠 채 날짜가 빈 업무는 **빈 채로 남는다** — 전에는 없던 날짜를 얻었다 |
| 다 | 저장 전에 보이는 **갈래별 수**가 실제와 같다 · 기간만 고친 것이 따로 세어지나 |
| 라 | 부딪히면 **나중 것**이 이긴다 — 양쪽 다 |
| 마 | **물러선 쪽이 안 지워진다** — 실제로 되돌려서 잰다 |
| 바 | 이미 선 업무는 **「안 옮김」** 으로 시작한다 |

**합성 자료만 씁니다** — 운영 DB 는 시험이 열지 않습니다. 운영에서 센 값은
읽기 전용으로 따로 읽었고 보고에 있습니다.

**수를 시험에 박지 않습니다** — 자료를 세어 기대값을 만듭니다(다).

각 독스트링에 **그 줄이 실제로 무엇을 보는지** 적습니다 — 막혀야 할 것이
막히는가 · 막히면 안 되는 것이 통과하는가 · 검사가 볼 것을 보고 있는가(11-3).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.domain import library as lib_domain
from app.models import Department, Retreat, TaskLibrary, TaskRun
from tests.conftest import app_session

첫개회 = dt.date(2027, 8, 20)
새개회 = dt.date(2027, 9, 17)          # 넉 주 뒤 · 같은 금요일
끈날 = 3                                # 사람이 사흘 미뤄 둔다


def _d1주(개회: dt.date) -> dt.date:
    return 개회 - dt.timedelta(days=(개회.weekday() + 1) % 7)


def _그주(개회: dt.date, d_week: int) -> dt.date:
    return _d1주(개회) - dt.timedelta(days=(d_week - 1) * 7)


@pytest.fixture
def 회차(admin_client):
    """회차 하나 + 업무 넷 — 켠 것 셋(그중 하나는 날짜가 빔), 뺀 것 하나.

    **날짜가 빈 켠 업무를 일부러 둡니다** — AW-c 가 밟히는 조건이고, 운영에는
    지금 하나도 없어서(읽어서 셌습니다) 합성으로만 잴 수 있습니다.
    """
    with app_session() as db:
        r = Retreat(name="2027 여름수련회", start_date=첫개회,
                    end_date=첫개회 + dt.timedelta(days=2))
        db.add(r)
        db.flush()
        dept = Department(retreat_id=r.id, key="seongyo", name="3 선교사회", sort_order=0)
        db.add(dept)
        db.flush()
        # (D-주차, 켤까, 그 주 일요일에서 며칠, 며칠짜리, 날짜를 넣을까)
        차림 = [(13, True, 3, 3, True), (8, True, 0, 6, True),
               (5, False, 0, 0, True), (10, True, 0, 0, False)]
        for i, (dw, inc, 오프셋, 기간, 날짜있음) in enumerate(차림):
            lib = TaskLibrary(title=f"업무 {i}", kind="main", date_anchor="week",
                              default_d_week=dw, default_offset_days=오프셋,
                              default_span_days=기간)
            db.add(lib)
            db.flush()
            시작 = (_그주(첫개회, dw) + dt.timedelta(days=오프셋)) if 날짜있음 else None
            db.add(TaskRun(library_id=lib.id, retreat_id=r.id, included=inc,
                           run_no=i + 1, d_week=dw if 날짜있음 else None,
                           department_id=dept.id,
                           start_date=시작,
                           end_date=(시작 + dt.timedelta(days=기간)) if 시작 else None))
        db.commit()
        return r.id


def _줄들(rid: int):
    with app_session() as db:
        return {r.run_no: r for r in
                db.scalars(select(TaskRun).where(TaskRun.retreat_id == rid)).all()}


def _값(rid: int):
    with app_session() as db:
        return {r.run_no: (r.start_date, r.end_date, r.moved_offset_days, r.moved_at)
                for r in db.scalars(select(TaskRun).where(TaskRun.retreat_id == rid)).all()}


def _run_id(rid: int, no: int) -> int:
    return _줄들(rid)[no].id


def _끈다(client, rid: int, no: int, 며칠: int):
    """보드에서 바를 끄는 그 길로 옮긴다 — **DB 에 직접 쓰지 않습니다.**

    직접 쓰면 `moved_offset_days` 가 안 붙어 「안 옮김」 이 되고, 그러면
    이 시험이 재려던 것을 아예 안 재게 됩니다.
    """
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == rid, TaskRun.run_no == no)).first()
        새시작 = run.start_date + dt.timedelta(days=며칠)
        새끝 = (run.end_date or run.start_date) + dt.timedelta(days=며칠)
    답 = client.post(f"/board/task/{_run_id(rid, no)}/dates",
                    json={"start": 새시작.isoformat(), "end": 새끝.isoformat()})
    assert 답.status_code == 200, 답.text
    return 새시작


def _개회일을바꾼다(client, rid: int, 개회: dt.date):
    return client.post(f"/retreats/{rid}/update", data={
        "name": "2027 여름수련회",
        "start_date": 개회.isoformat(),
        "end_date": (개회 + dt.timedelta(days=2)).isoformat(),
        "meal_subsidy_per_person": 8000,
    }, follow_redirects=False)


def _라이브러리를고친다(rid: int, no: int, 새주차: int):
    """라이브러리의 D-주차를 고친다 — `dates_changed_at` 이 찍히는 그 길로."""
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == rid, TaskRun.run_no == no)).first()
        lib = run.library
        from app.models import _now
        lib.default_d_week = 새주차
        lib.dates_changed_at = _now()
        db.commit()


# ── 가. 옮긴 것은 밀고 안 옮긴 것은 다시 센다 ─────────────────────────


def test39_a01_옮긴_업무는_같은_간격을_지키고_안_옮긴_업무는_다시_셈해진다(admin_client, 회차):
    """가) **둘을 같은 판에서 봅니다.** 한쪽만 재면 「전부 미는 것」 과
    「전부 다시 세는 것」 을 구별하지 못합니다 — 둘 다 한쪽 시험은 통과합니다.

    봅니다 — ① 끌어 옮긴 값이 실제로 저장되나(안 그러면 뒤가 무의미)
    ② `moved_offset_days` 에 **며칠인지가** 남나 ③ 개회일을 바꾼 뒤 옮긴
    업무가 **새 개회일 셈 + 같은 며칠** 자리에 서나 ④ **기간(길이)이
    그대로인가** ⑤ 안 옮긴 업무는 **라이브러리 셈 그대로**인가
    ⑥ 뺀 업무는 안 건드려지나.
    """
    끈자리 = _끈다(admin_client, 회차, 1, 끈날)
    앞 = _값(회차)
    assert 앞[1][0] == 끈자리, "① 끈 값이 안 저장된다"
    assert 앞[1][2] == 끈날, f"② 며칠인지가 안 남는다: {앞[1][2]}"
    안옮긴앞, 뺀것앞 = 앞[2], 앞[3]

    assert _개회일을바꾼다(admin_client, 회차, 새개회).status_code == 303
    뒤 = _값(회차)

    with app_session() as db:
        run1 = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 1)).first()
        셈1, 셈1끝 = lib_domain.library_dates(run1.library, 새개회)
        run2 = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 2)).first()
        셈2, 셈2끝 = lib_domain.library_dates(run2.library, 새개회)

    assert 뒤[1][0] == 셈1 + dt.timedelta(days=끈날), \
        f"③ 옮긴 업무가 같은 간격을 안 지켰다: {뒤[1][0]} (셈 {셈1} + {끈날}일)"
    assert 뒤[1][1] - 뒤[1][0] == 앞[1][1] - 앞[1][0], "④ 기간이 바뀌었다"
    assert 뒤[1][0] != 셈1, "③ 옮긴 자리가 셈한 자리와 같다 — 이 시험이 아무것도 안 잰다"

    assert (뒤[2][0], 뒤[2][1]) == (셈2, 셈2끝), \
        f"⑤ 안 옮긴 업무가 라이브러리 셈과 다르다: {뒤[2][0]} vs {셈2}"
    assert 뒤[2][0] != 안옮긴앞[0], "⑤ 안 옮긴 업무가 아예 안 움직였다"
    assert (뒤[3][0], 뒤[3][1]) == (뺀것앞[0], 뺀것앞[1]), "⑥ 뺀 업무가 건드려졌다"


# ── 나. 날짜가 빈 채 켜진 업무 (AW-c) ─────────────────────────────────


def test39_b01_날짜가_빈_채_켜진_업무는_빈_채로_남는다(admin_client, 회차):
    """나) 전에는 `d_week or FIRST_D_WEEK` 로 떨어져 **없던 날짜를 얻었습니다**
    (봐둘것 AW-c). 4-13 이 「날짜 없는 업무」 를 따로 모아 두기로 한 자리가
    개회일을 한 번 바꾸면 조용히 비었습니다.

    봅니다 — ① 바꾸기 전에 비어 있었나 ② 바꾼 뒤에도 비어 있나
    ③ **셀 수 있는데 안 채운 것인가** — 라이브러리 셈이 실제 날짜를 내는지
    확인합니다. 못 세는 것이라 안 채운 것이면 이 줄은 아무것도 안 잽니다
    ④ 같은 판의 다른 업무는 움직였나(개회일이 실제로 바뀐 것이 맞나).
    """
    앞 = _값(회차)
    assert 앞[4][0] is None, "① 처음부터 비어 있지 않다"

    assert _개회일을바꾼다(admin_client, 회차, 새개회).status_code == 303
    뒤 = _값(회차)
    assert 뒤[4][0] is None and 뒤[4][1] is None, f"② 없던 날짜를 얻었다: {뒤[4]}"

    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 4)).first()
        셈, _ = lib_domain.library_dates(run.library, 새개회)
    assert isinstance(셈, dt.date), "③ 셀 수가 없어서 안 채운 것이면 이 줄은 아무것도 안 잰다"
    assert 뒤[2][0] != 앞[2][0], "④ 개회일이 안 바뀌었다 — 이 판이 아무것도 안 했다"


# ── 다. 저장 전에 보이는 갈래별 수 ────────────────────────────────────


def test39_c01_저장_전에_보이는_갈래별_수가_실제와_같다(admin_client, 회차):
    """다) **수를 시험에 박지 않습니다** — 자료를 세어 기대값을 만듭니다.
    박으면 차림을 한 줄 고칠 때 시험이 막고, 그 막힘은 고장이 아닙니다.

    봅니다 — ① 미리보기가 네 값을 다 내는가 ② **실제로 저장한 뒤 달라진
    수와 같은가**(이것이 이 줄의 전부입니다 — 미리보기만 재면 그 수가
    맞는지는 아무도 안 봅니다) ③ 같은 개회일이면 「달라질 것 없음」 인가
    ④ 셋이 다 0 이 아닌가 — 전부 0 이면 아무것도 안 재는 판입니다.
    """
    _끈다(admin_client, 회차, 1, 끈날)
    앞 = _값(회차)

    답 = admin_client.get(f"/retreats/{회차}/reschedule-preview?open_date={새개회.isoformat()}")
    assert 답.status_code == 200, 답.text
    본것 = 답.json()
    assert 본것["changed"] is True
    assert {"다시셈", "밀기", "기간만", "빈채"} <= set(본것), f"① 네 값이 다 없다: {본것}"

    같은날 = admin_client.get(
        f"/retreats/{회차}/reschedule-preview?open_date={첫개회.isoformat()}").json()
    assert 같은날 == {"changed": False}, f"③ 같은 개회일인데 달라진다고 한다: {같은날}"

    assert _개회일을바꾼다(admin_client, 회차, 새개회).status_code == 303
    뒤 = _값(회차)

    실제 = {"다시셈": 0, "밀기": 0, "기간만": 0, "빈채": 0}
    with app_session() as db:
        for run in db.scalars(select(TaskRun).where(TaskRun.retreat_id == 회차)).all():
            no = run.run_no
            if not run.included:
                continue
            if 앞[no][0] is None:
                실제["빈채"] += 1
                continue
            if (뒤[no][0], 뒤[no][1]) == (앞[no][0], 앞[no][1]):
                continue
            셈, 셈끝 = lib_domain.library_dates(run.library, 새개회)
            if 앞[no][2] is None or (뒤[no][0], 뒤[no][1]) == (셈, 셈끝):
                실제["다시셈"] += 1      # 손 자리에서 남는 것이 없다
            elif 앞[no][2]:
                실제["밀기"] += 1        # 며칠이 0 이 아니다
            else:
                실제["기간만"] += 1      # 자리는 그대로, 길이만 지켜진다
    assert {k: 본것[k] for k in 실제} == 실제, f"② 보여준 수와 실제가 다르다: {본것} vs {실제}"
    assert 실제["다시셈"] and 실제["밀기"] and 실제["빈채"], \
        f"④ 세 갈래 중 0 이 있다 — 그 갈래를 안 쟀다: {실제}"


def _기간만늘린다(client, rid: int, no: int, 며칠: int):
    """**자리는 그대로 두고 마감일만 뒤로.** 드로어에서 하는 그 일이고,
    같은 엔드포인트로 들어옵니다(4-6) — 그래서 이것도 「손으로 정한 자리」 로
    남고 며칠은 0 입니다."""
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == rid, TaskRun.run_no == no)).first()
        시작 = run.start_date
        새끝 = (run.end_date or run.start_date) + dt.timedelta(days=며칠)
    답 = client.post(f"/board/task/{_run_id(rid, no)}/dates",
                    json={"start": 시작.isoformat(), "end": 새끝.isoformat()})
    assert 답.status_code == 200, 답.text
    return 시작


def test39_c02_기간만_고친_것과_자리를_옮긴_것이_한_수에_안_들어간다(admin_client, 회차):
    """다) **부풀림을 잽니다** (2026-09-12 에 사람이 재라고 한 자리).

    드로어에서 마감일만 고쳐도 같은 엔드포인트로 들어오므로 「손으로 정한
    자리」 가 됩니다. 그 둘이 한 수에 들어가면 **「자리를 민 업무 N건」 이
    실제로 민 것보다 크고**, 사람이 그 수를 보고 판단할 수 없습니다.

    **수를 시험에 박지 않습니다** — 자료를 세어 기대값을 만듭니다.

    봅니다 — ① 둘 다 「손으로 정한 자리」 로 남나(며칠 0 과 0 아님)
    ② 미리보기가 **둘을 다른 수로** 내나 ③ **합치면 부풀던 그 수가 되나**
    — 가르기 전에는 이 둘이 한 수였다는 증거입니다 ④ 기간만 고친 쪽이
    실제로 자리는 그대로이고 길이만 지켜지나.
    """
    _끈다(admin_client, 회차, 1, 끈날)
    _기간만늘린다(admin_client, 회차, 2, 2)
    앞 = _값(회차)
    assert 앞[1][2] == 끈날 and 앞[2][2] == 0, \
        f"① 둘 중 하나가 「손으로 정한 자리」 로 안 남았다: {앞[1][2]} · {앞[2][2]}"

    본것 = admin_client.get(
        f"/retreats/{회차}/reschedule-preview?open_date={새개회.isoformat()}").json()

    # 기대값을 자료에서 만든다 — 며칠이 0 이 아닌 것과 0 인 것
    with app_session() as db:
        손자리 = [r for r in db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차)).all()
            if r.included and r.start_date and r.moved_offset_days is not None]
        민것 = sum(1 for r in 손자리 if r.moved_offset_days)
        기간만 = len(손자리) - 민것
    assert 민것 and 기간만, f"③ 한쪽이 0 이라 가른 뜻이 없다: {민것} · {기간만}"

    assert 본것["밀기"] == 민것, f"② 민 수가 다르다: {본것['밀기']} vs {민것}"
    assert 본것["기간만"] == 기간만, f"② 기간만 지킬 수가 다르다: {본것['기간만']} vs {기간만}"
    assert 본것["밀기"] + 본것["기간만"] == len(손자리), \
        "③ 합이 「손으로 정한 자리」 전부와 안 맞는다 — 가르기 전 그 수다"

    # ④ 실제로 저장해 보고 확인한다
    _개회일을바꾼다(admin_client, 회차, 새개회)
    with app_session() as db:
        run2 = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 2)).first()
        셈, 셈끝 = lib_domain.library_dates(run2.library, 새개회)
        선자리, 선끝 = run2.start_date, run2.end_date
    assert 선자리 == 셈, f"④ 자리가 밀렸다: {선자리} vs {셈}"
    assert 선끝 != 셈끝, "④ 늘려 둔 기간이 라이브러리 길이로 되돌아갔다"


# ── 라. 부딪히면 나중 것이 이긴다 ─────────────────────────────────────


def test39_d01_옮긴_뒤_라이브러리를_고치면_라이브러리가_이긴다(admin_client, 회차):
    """라) 사람이 2026-09-12 에 「나중 것이 이긴다」 로 정했습니다.

    봅니다 — ① 고치기 전에는 옮긴 자리를 따르는가(그 상태를 안 거치면
    ② 가 무엇 때문에 바뀐 것인지 알 수 없습니다) ② 라이브러리를 나중에
    고치면 **라이브러리 자리로 서는가** ③ 화면이 그것을 말하는가
    (`moved.why == 'library'`) ④ **옮긴 값이 안 지워지는가.**
    """
    _끈다(admin_client, 회차, 1, 끈날)
    상세 = admin_client.get(f"/board/task/{_run_id(회차, 1)}").json()
    assert 상세["moved"]["hand"] is True, "① 옮긴 직후인데 안 따른다"

    _라이브러리를고친다(회차, 1, 새주차=11)
    assert _개회일을바꾼다(admin_client, 회차, 새개회).status_code == 303

    뒤 = _값(회차)
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 1)).first()
        셈, _ = lib_domain.library_dates(run.library, 새개회)
    assert 뒤[1][0] == 셈, f"② 라이브러리가 안 이겼다: {뒤[1][0]} vs {셈}"

    상세 = admin_client.get(f"/board/task/{_run_id(회차, 1)}").json()
    assert 상세["moved"]["hand"] is False and 상세["moved"]["why"] == "library", \
        f"③ 화면이 어느 쪽이 이겼는지 안 말한다: {상세['moved']}"
    assert 뒤[1][2] == 끈날, f"④ 물러선 쪽이 지워졌다: {뒤[1][2]}"


def test39_d02_라이브러리를_고친_뒤_옮기면_옮긴_것이_이긴다(admin_client, 회차):
    """라) **반대쪽입니다.** 앞 줄만 있으면 「라이브러리가 늘 이긴다」 와
    구별되지 않습니다 — 고친 것이 시각이 아니라 우선순위였을 수 있습니다.

    봅니다 — ① 라이브러리를 먼저 고쳐도 ② 그 뒤에 끌면 옮긴 자리를 따르나
    ③ 개회일을 바꿔도 **같은 간격**을 지키나 ④ 화면이 그렇게 말하나.
    """
    _라이브러리를고친다(회차, 1, 새주차=11)
    _끈다(admin_client, 회차, 1, 끈날)

    상세 = admin_client.get(f"/board/task/{_run_id(회차, 1)}").json()
    assert 상세["moved"]["hand"] is True, f"② 옮긴 것이 안 이겼다: {상세['moved']}"

    # **간격은 「끈 며칠」 이 아니라 저장된 값입니다.** 여기서는 라이브러리를
    # 먼저 D-11주로 고쳤으므로, 끌기 전부터 run 이 이미 라이브러리 셈에서
    # 두 주 떨어져 있었습니다 — 끈 뒤의 간격은 그 둘을 더한 값입니다.
    # 끈날 을 박으면 이 줄은 **차림이 바뀔 때 고장으로 보이는 실패**를 냅니다
    간격 = _값(회차)[1][2]
    assert 간격 is not None, "② 간격이 안 남았다"

    assert _개회일을바꾼다(admin_client, 회차, 새개회).status_code == 303
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 1)).first()
        셈, _ = lib_domain.library_dates(run.library, 새개회)
    assert _값(회차)[1][0] == 셈 + dt.timedelta(days=간격), "③ 같은 간격을 안 지켰다"
    assert 간격 != 0, "③ 간격이 0 이면 라이브러리를 따른 것과 구별되지 않는다"
    assert admin_client.get(f"/board/task/{_run_id(회차, 1)}").json()["moved"]["why"] == "hand", \
        "④ 화면이 다른 말을 한다"


# ── 마. 물러선 쪽이 안 지워지고, 되돌아간다 ───────────────────────────────


def test39_e01_물러선_쪽이_안_지워지고_실제로_되돌아간다(admin_client, 회차):
    """마) **말로만 「되돌릴 수 있다」 고 적지 않습니다** — 실제로 되돌려서
    잽니다. 되돌리는 길이 없으면 「지우지 않았다」 는 아무 뜻이 없습니다.

    봅니다 — ① 라이브러리가 이긴 상태에서 ② 「옮긴 자리로」 를 누르면
    **끈 자리로 돌아오는가** ③ 그때도 라이브러리 자리는 여전히 셀 수 있는가
    (물러선 쪽이 안 지워졌다는 말의 반대편) ④ 다시 「기본 자리로」 를 누르면
    라이브러리 자리로 가고 **옮긴 값은 여전히 남는가** ⑤ 옮긴 적이 없는
    업무에는 이 길이 **막히는가.**
    """
    _끈다(admin_client, 회차, 1, 끈날)
    _라이브러리를고친다(회차, 1, 새주차=11)
    _개회일을바꾼다(admin_client, 회차, 새개회)
    rid1 = _run_id(회차, 1)
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(TaskRun.id == rid1)).first()
        셈, _ = lib_domain.library_dates(run.library, 새개회)
    assert _값(회차)[1][0] == 셈, "① 라이브러리가 이긴 상태가 아니다"

    답 = admin_client.post(f"/board/task/{rid1}/dates/follow", json={"hand": True})
    assert 답.status_code == 200, 답.text
    assert _값(회차)[1][0] == 셈 + dt.timedelta(days=끈날), "② 옮긴 자리로 안 돌아왔다"
    assert 답.json()["moved"]["why"] == "hand"

    답 = admin_client.post(f"/board/task/{rid1}/dates/follow", json={"hand": False})
    assert 답.status_code == 200, 답.text
    뒤 = _값(회차)
    assert 뒤[1][0] == 셈, "④ 기본 자리로 안 갔다"
    assert 뒤[1][2] == 끈날, "④ 옮긴 값이 지워졌다"
    assert 답.json()["moved"]["why"] == "dropped"

    막힘 = admin_client.post(f"/board/task/{_run_id(회차, 2)}/dates/follow", json={"hand": True})
    assert 막힘.status_code == 400, f"⑤ 옮긴 적 없는 업무에 길이 열려 있다: {막힘.status_code}"


def test39_e02_되돌린_것이_활동_기록에_남는다(admin_client, 회차):
    """마) 되돌린 것도 사실입니다 — 안 남기면 「왜 자리가 바뀌었지」 를
    나중에 아무도 설명하지 못합니다 (4-12 의 그 자리와 같은 판단).

    봅니다 — ① 되돌리면 기록이 한 줄 생기나 ② 그 줄이 **어느 쪽으로
    갔는지**를 담고 있나.
    """
    from app.models import ActivityLog
    _끈다(admin_client, 회차, 1, 끈날)
    admin_client.post(f"/board/task/{_run_id(회차, 1)}/dates/follow", json={"hand": False})
    with app_session() as db:
        줄 = db.scalars(select(ActivityLog).where(
            ActivityLog.action == "업무_날짜_기준_변경")).all()
    assert len(줄) == 1, f"① 기록이 {len(줄)}줄이다"
    assert "라이브러리" in (줄[0].summary or ""), f"② 어느 쪽인지 안 적혔다: {줄[0].summary}"


def test39_e03_남의_부서_업무는_되돌리지_못한다(admin_client, client, 회차):
    """마) **막는 코드에 막히는 쪽 시험이 함께 있어야 합니다**(11-3).
    날짜를 바꾸는 길이고 부서 경계를 넘습니다 — 같은 성격의 다른 쓰기
    엔드포인트(`/status` · `/dates`)에는 그 짝이 있는데 이 새 길에만
    없었습니다 (2026-09-12 검토가 짚었습니다).

    봅니다 — ① 남의 부서 사람에게 403 인가 ② **막힌 뒤에도 값이 그대로인가**
    (거절하면서 절반만 쓰지 않았는가) ③ 관리자에게는 같은 요청이 통하나 —
    안 그러면 「늘 막는 문」 이라 ① 이 아무것도 안 잽니다.
    """
    _끈다(admin_client, 회차, 1, 끈날)
    앞 = _값(회차)[1]
    rid1 = _run_id(회차, 1)

    from tests.conftest import login_as
    login_as(client, "01099998888", name="남의 부서 사람")
    막힘 = client.post(f"/board/task/{rid1}/dates/follow", json={"hand": False})
    assert 막힘.status_code == 403, f"① 남의 부서인데 {막힘.status_code} 다"
    assert _값(회차)[1] == 앞, "② 막혔는데 값이 바뀌었다"

    통함 = admin_client.post(f"/board/task/{rid1}/dates/follow", json={"hand": False})
    assert 통함.status_code == 200, f"③ 관리자에게도 막힌다 — ① 이 아무것도 안 잰다"


def test39_d03_라이브러리를_고친_직후에는_아직_그_자리에_안_선다(admin_client, 회차):
    """라) **개회일이 바뀌기 전 구간**입니다. `edit_library_task` 는 run 을
    안 건드리므로(「이미 치른 회차의 실행 기록은 건드리지 않는다」), 라이브러리를
    고친 순간 **판정은 뒤집히지만 날짜는 손 자리 그대로**입니다.

    그때 화면이 「그쪽을 따르고 있습니다」 라고 하면 바로 위 기간과 두 말을
    합니다 — 2026-09-12 검토가 짚었고, 문구를 미래형으로 갈랐습니다.
    **운영에서는 개회일을 바꾸는 일보다 라이브러리를 고치는 일이 잦으므로
    이 구간이 기본 상태에 가깝습니다.**

    봅니다 — ① 판정이 뒤집혔나 ② **날짜는 아직 손 자리인가**
    ③ 화면이 그 둘을 구별하는 값을 내는가(`at_library` 가 거짓)
    ④ 개회일을 바꾸면 그때 실제로 라이브러리 자리에 서고 ③ 이 참이 되는가.
    """
    끈자리 = _끈다(admin_client, 회차, 1, 끈날)
    _라이브러리를고친다(회차, 1, 새주차=11)

    상세 = admin_client.get(f"/board/task/{_run_id(회차, 1)}").json()
    assert 상세["moved"]["why"] == "library", "① 판정이 안 뒤집혔다"
    assert _값(회차)[1][0] == 끈자리, "② 날짜가 벌써 움직였다"
    assert 상세["moved"]["at_library"] is False, \
        f"③ 아직 그 자리가 아닌데 그렇다고 말한다: {상세['moved']}"

    _개회일을바꾼다(admin_client, 회차, 새개회)
    상세 = admin_client.get(f"/board/task/{_run_id(회차, 1)}").json()
    assert 상세["moved"]["at_library"] is True, "④ 옮긴 뒤에도 그 자리가 아니라고 한다"


# ── 바. 이미 선 업무는 「안 옮김」 으로 시작한다 ───────────────────────


def test39_f01_마이그레이션_뒤에_옮긴_것으로_표시된_업무가_없다(admin_client, 회차):
    """바) 부팅은 **칸을 붙이기만** 합니다. 값을 채우면 **지어낸 기록**이
    됩니다(6-9) — 지금 날짜가 라이브러리 셈과 다르다고 해서 사람이 옮긴
    것이라고 단정할 수 없습니다. 라이브러리를 나중에 고쳤어도 그렇게 됩니다.

    봅니다 — ① 세 칸이 `_ADDED_COLUMNS` 에 있나(붙는 길이 실재하나)
    ② 실제 표에 칸이 붙어 있나 ③ **옮긴 것으로 표시된 업무가 하나도
    없나** ④ 센 업무 수가 0 이 아닌가 — 0 이면 ③ 이 아무것도 안 봅니다.
    """
    from sqlalchemy import text

    from app.db import _ADDED_COLUMNS, engine

    for 칸 in (("task_runs", "moved_offset_days", "INTEGER"),
              ("task_runs", "moved_at", "DATETIME"),
              ("task_library", "dates_changed_at", "DATETIME")):
        assert 칸 in _ADDED_COLUMNS, f"① {칸} 이 붙는 길에 없다"

    with engine.connect() as conn:
        runs = {row[1] for row in conn.execute(text("PRAGMA table_info(task_runs)"))}
        libs = {row[1] for row in conn.execute(text("PRAGMA table_info(task_library)"))}
    assert {"moved_offset_days", "moved_at"} <= runs, "② task_runs 에 칸이 없다"
    assert "dates_changed_at" in libs, "② task_library 에 칸이 없다"

    with app_session() as db:
        전부 = db.scalars(select(TaskRun)).all()
        옮긴것 = [r for r in 전부 if r.moved_offset_days is not None]
    assert 전부, "④ 셀 업무가 없다 — ③ 이 아무것도 안 본다"
    assert not 옮긴것, f"③ 옮긴 것으로 표시된 업무가 {len(옮긴것)}건 있다"


def test39_f02_DB_에_직접_넣은_날짜는_옮긴_것이_아니다(admin_client, 회차):
    """바) **경계입니다.** 「옮김」 은 화면(`/dates`)을 지난 것뿐입니다.
    스크립트나 시험이 DB 에 직접 쓴 날짜는 그 사실이 안 남고, 개회일이
    바뀌면 라이브러리 셈으로 돌아갑니다 — 이 판 전의 동작 그대로입니다.

    안 적어 두면 다음 사람이 「옮겨 뒀는데 왜 돌아갔지」 를 여기서 만납니다.

    봅니다 — ① 직접 쓴 날짜가 저장되나 ② 그래도 「안 옮김」 인가
    ③ 개회일을 바꾸면 라이브러리 셈으로 돌아가나.
    """
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 1)).first()
        run.start_date = run.start_date + dt.timedelta(days=2)
        db.commit()
    assert _값(회차)[1][2] is None, "② 직접 쓴 것이 「옮김」 으로 잡혔다"

    _개회일을바꾼다(admin_client, 회차, 새개회)
    with app_session() as db:
        run = db.scalars(select(TaskRun).where(
            TaskRun.retreat_id == 회차, TaskRun.run_no == 1)).first()
        셈, _ = lib_domain.library_dates(run.library, 새개회)
    assert _값(회차)[1][0] == 셈, "③ 라이브러리 셈으로 안 돌아갔다"
