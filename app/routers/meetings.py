"""회의록 — 안건/결정사항/액션아이템 기록과 Task 전환.

회의 따로, 실행 따로가 되지 않도록 액션아이템은 한 번의 클릭으로 Task가 된다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import notifications as notify_service
from app.db import SessionLocal, get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from pydantic import BaseModel

from app.models import (
    MEETING_ITEM_KINDS,
    Department,
    DiscussionEntry,
    Meeting,
    MeetingItem,
    Retreat,
    Task,
    TaskRun,
    User,
)
from app.domain import permissions as perm
from app.security import get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter(prefix="/meetings")


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


def parse_attendees(raw: str) -> list[str]:
    if not raw:
        return []
    return [name for name in re.split(r"[,\n\r\t ]+", raw.strip()) if name]


def _owned(db: Session, meeting_id: int, retreat: Retreat) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    if meeting.retreat_id is not None and meeting.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return meeting


@router.get("")
def meeting_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    meetings = list(
        db.scalars(
            select(Meeting)
            .where((Meeting.retreat_id == retreat.id) | (Meeting.retreat_id.is_(None)))
            .order_by(Meeting.meeting_date.is_(None), Meeting.meeting_date.desc(), Meeting.id.desc())
        )
    )
    return render(
        request,
        "meetings.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "meetings": meetings,
            "today": dt.date.today().isoformat(),
            "active_tab": "meetings",
            "can_edit": not perm.is_readonly(user.role),
        },
    )


@router.get("/{meeting_id}")
def meeting_detail(
    meeting_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    return render(
        request,
        "meeting_detail.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "meeting": meeting,
            "active_tab": "meetings",
            "can_edit": not perm.is_readonly(user.role),
            "kinds": MEETING_ITEM_KINDS,
            "departments": list(
                db.scalars(
                    select(Department)
                    .where(Department.retreat_id == retreat.id)
                    .order_by(Department.sort_order, Department.id)
                )
            ),
            "members": list(
                db.scalars(select(User).where(User.is_active).order_by(User.name))
            ),
        },
    )


@router.post("/create")
def create_meeting(
    title: str = Form(...),
    meeting_date: str = Form(""),
    attendees: str = Form(""),
    body: str = Form(""),
    # 빈 문자열은 클라이언트에 따라 아예 전송되지 않을 수 있으므로
    # "연결 안 함"을 명시적인 토큰으로 받는다.
    link_retreat: str = Form("retreat"),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = Meeting(
        # 수련회와 무관한 일반 회의는 회차에 연결하지 않는다 (검색·필터로 구분)
        retreat_id=None if link_retreat == "none" else retreat.id,
        title=title.strip(),
        meeting_date=_parse_date(meeting_date) or dt.date.today(),
        attendee_names=parse_attendees(attendees),
        body=body.strip() or None,
        created_by_id=user.id,
    )
    db.add(meeting)
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회의록_생성",
        target_type="meeting",
        target_id=meeting.id,
        summary=meeting.title,
    )
    return redirect(f"/meetings/{meeting.id}?retreat_id={retreat.id}", message="회의록을 만들었습니다.")


@router.post("/{meeting_id}/items")
def add_item(
    meeting_id: int,
    kind: str = Form(...),
    content: str = Form(...),
    department_id: str = Form(""),
    assignee_id: str = Form(""),
    due_date: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    if kind not in MEETING_ITEM_KINDS:
        raise HTTPException(status_code=400, detail="알 수 없는 항목 종류입니다.")

    max_order = (
        db.scalar(
            select(func.max(MeetingItem.sort_order)).where(MeetingItem.meeting_id == meeting.id)
        )
        or 0
    )
    db.add(
        MeetingItem(
            meeting_id=meeting.id,
            kind=kind,
            content=content.strip(),
            department_id=int(department_id) if department_id else None,
            assignee_id=int(assignee_id) if assignee_id else None,
            due_date=_parse_date(due_date),
            sort_order=max_order + 1,
        )
    )
    db.commit()
    return redirect(f"/meetings/{meeting.id}?retreat_id={retreat.id}", message="항목을 추가했습니다.")


@router.post("/items/{item_id}/to-task")
def convert_to_task(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    item = db.get(MeetingItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    if item.converted_task_id is not None:
        return redirect(
            f"/meetings/{item.meeting_id}?retreat_id={retreat.id}",
            message="이미 할 일로 등록된 항목입니다.",
        )

    task = Task(
        retreat_id=retreat.id,
        title=item.content[:200],
        description=f"[회의록] {item.meeting.title} ({item.meeting.meeting_date})",
        department_id=item.department_id,
        assignee_id=item.assignee_id,
        due_date=item.due_date,
        status="대기",
        blocked_by_task_ids=[],
        related_department_ids=[],
    )
    db.add(task)
    db.flush()
    item.converted_task_id = task.id
    db.commit()

    if task.assignee_id:
        assignee = db.get(User, task.assignee_id)
        if assignee is not None:
            notify_service.notify(
                db,
                users=[assignee],
                retreat_id=retreat.id,
                kind="할일배정",
                title=f"📋 새 할 일 · {task.title}",
                body=f"'{item.meeting.title}' 회의의 액션아이템이 할 일로 등록됐습니다.",
                link=f"/tasks?retreat_id={retreat.id}",
                target_type="task",
                target_id=task.id,
                dedupe_key=f"task-assigned:{task.id}",
                exclude_user_id=user.id,
            )

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="액션아이템_할일전환",
        target_type="task",
        target_id=task.id,
        summary=task.title,
    )
    return redirect(
        f"/meetings/{item.meeting_id}?retreat_id={retreat.id}", message="할 일로 등록했습니다."
    )


@router.post("/items/{item_id}/delete")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    item = db.get(MeetingItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    meeting_id = item.meeting_id
    db.delete(item)
    db.commit()
    return redirect(f"/meetings/{meeting_id}?retreat_id={retreat.id}", message="항목을 삭제했습니다.")


@router.post("/{meeting_id}/update")
def update_meeting(
    meeting_id: int,
    background: BackgroundTasks,
    title: str = Form(...),
    meeting_date: str = Form(""),
    attendees: str = Form(""),
    body: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    meeting.title = title.strip()
    meeting.meeting_date = _parse_date(meeting_date)
    meeting.attendee_names = parse_attendees(attendees)
    meeting.body = body.strip() or None
    db.commit()
    # **저장은 여기서 끝난다.** 분석은 뒤에서 돈다 (5단계)
    분석_걸어둔다(background, meeting, db)
    return redirect(f"/meetings/{meeting.id}?retreat_id={retreat.id}", message="회의록을 저장했습니다.")


@router.post("/{meeting_id}/delete")
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    title = meeting.title
    db.delete(meeting)
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회의록_삭제",
        target_type="meeting",
        target_id=meeting_id,
        summary=title,
    )
    return redirect(f"/meetings?retreat_id={retreat.id}", message="회의록을 삭제했습니다.")


# ==========================================================================
# 회의록을 읽고 제안하기 (CLAUDE.md 회의록 4단계)
#
# **읽고 제안하는 곳은 `domain/suggest.py` 하나다.** 여기는 그것을 화면에
# 실어 보내고, 사람이 고른 것만 반영하는 창구일 뿐이다.
#
# **아무것도 자동으로 반영되지 않는다.** 사람이 하나씩 고른다.
# 고른 것에는 **출처 회의록**이 남고 `ActivityLog` 에 `actor_type='claude'`
# 로 기록된다 — 나중에 "이건 누가 넣었지" 를 물을 수 있어야 한다.


def discussion_body(meeting: Meeting) -> str:
    """그 업무의 논의로 **정확히 무엇이 적히는가.**

    **누르기 전에 볼 수 있어야 한다** — 4-10 이 "무엇을 보고 그렇게 말하는지
    함께 보인다" 고 한 자리와 같다. 그래서 만드는 곳을 하나로 두고, 미리보기와
    실제 저장이 **같은 함수**를 쓴다. 두 벌이 되면 보여준 것과 남는 것이
    갈리고, 갈린 쪽을 아무도 눈치채지 못한다.
    """
    날 = meeting.meeting_date.isoformat() if meeting.meeting_date else "날짜 없음"
    출처 = f"[회의록 {날} · {meeting.title}] 에서 옮김"
    return f"{출처}\n{(meeting.body or '').strip()}"


# ══════════════════════════════════════════════════════════════════
# 회의록을 문장으로 읽는다 (회의록 5단계)
# ══════════════════════════════════════════════════════════════════
#
# **저장은 분석을 기다리지 않는다.** 회의록을 저장하면 바로 화면이 돌아오고,
# 분석은 뒤에서 돈다. 기다리게 하면 사람은 저장이 고장난 줄 안다 —
# API 왕복이 몇 초에서 몇십 초다.
#
# **본문이 안 바뀌면 다시 부르지 않는다.** 오타 하나 고칠 때마다 돈이 나가면
# 아무도 안 고친다. 본문의 해시를 남기고 같으면 앞의 결과를 그대로 쓴다.


def body_hash(meeting: Meeting) -> str:
    """이 회의록의 지문. **본문만 본다** — 제목이나 참석자가 바뀌었다고
    다시 부를 이유가 없다."""
    return hashlib.sha256(((meeting.body or "").strip()).encode("utf-8")).hexdigest()


def _제안을_json(것들) -> str:
    return json.dumps([{
        "kind": x.kind, "text": x.text, "why": x.why,
        "run_id": x.run_id, "run_title": x.run_title,
        "quote": x.quote, "title": x.title,
        "parent_run_id": x.parent_run_id, "parent_title": x.parent_title,
        "department": x.department, "evidence": x.evidence,
    } for x in 것들], ensure_ascii=False)


def 분석_한번(meeting_id: int) -> None:
    """뒤에서 도는 분석. **제 세션을 연다** — 요청이 끝나면 그쪽 세션은 닫힌다.

    **여기서 터져도 화면은 살아 있어야 한다** (4-10 조건 8). 무엇이 터지든
    상태를 '실패' 로 적고 왜인지를 남긴다. 조용히 끝나면 화면은 영원히
    '읽는 중' 이다.
    """
    from app.domain.suggest import suggest_full

    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.retreat_id is None:
            return
        retreat = db.get(Retreat, meeting.retreat_id)
        if retreat is None:
            return
        지문 = body_hash(meeting)
        try:
            r = suggest_full(db, retreat=retreat, meeting=meeting,
                             as_of=meeting.meeting_date)
        except Exception as exc:                    # noqa: BLE001
            meeting.suggest_state = "실패"
            meeting.suggest_note = f"분석하지 못했습니다 — {exc.__class__.__name__}"
            meeting.suggest_hash = None             # 다음에 다시 시도한다
            meeting.suggest_at = dt.datetime.now()
            db.commit()
            return
        meeting.suggest_state = "됨"
        meeting.suggest_json = _제안을_json(r.제안들)
        meeting.suggest_note = f"{r.방식}|{r.말}"
        meeting.suggest_cost = r.원
        meeting.suggest_tokens = f"{r.입력토큰}/{r.출력토큰}"
        meeting.suggest_at = dt.datetime.now()
        # **지문은 언제나 남긴다.** 안 남기면 볼 때마다 "본문이 바뀐 것" 으로
        # 읽혀 다시 돌고, 화면이 영원히 '읽는 중' 이다 (실제로 그랬다).
        # 낱말로 물러선 것을 다시 읽게 하는 일은 `분석_걸어둔다` 가 맡는다 —
        # **키가 생겼을 때만** 다시 돈다.
        meeting.suggest_hash = 지문
        db.commit()
    finally:
        db.close()


def 낱말로_물러섰나(meeting: Meeting) -> bool:
    """지난번 결과가 낱말 겹침이었나. `suggest_note` 는 `방식|말` 이다."""
    return (meeting.suggest_note or "").startswith("낱말|")


def 다시_읽어야_하나(meeting: Meeting) -> bool:
    """다시 부를 이유가 있는가.

    둘뿐이다 — **본문이 바뀌었거나**, 지난번에 낱말로 물러섰는데 **그 사이
    키가 생겼거나.** 둘째가 없으면 키를 넣어도 옛 결과가 그대로 남아
    영영 문장으로 안 읽는다. 반대로 지문을 아예 안 남기면 볼 때마다 다시
    돌아서 화면이 영원히 '읽는 중' 이다 — 둘 다 겪었다.
    """
    if not meeting.suggest_hash or meeting.suggest_hash != body_hash(meeting):
        return True
    if 낱말로_물러섰나(meeting):
        from app.domain import llm as llm_mod

        return bool(llm_mod.read_key())
    return False


# **적는 동안은 부르지 않는다.** 회의록을 쓰면서 중간중간 저장하는 것이
# 자연스러운데, 본문이 한 글자만 바뀌어도 지문이 달라져 다시 부른다 —
# 오타 세 번 고치면 그만큼 값이 나간다. 저장하면 시각만 찍어 두고
# **잠잠해진 뒤에** 부른다.
#
# **앱 안에 스케줄러를 넣지 않는다** (4-11). 시간을 재는 것은 화면이다 —
# 열려 있는 화면이 3초마다 물어보므로, 그때 "이제 됐나" 를 함께 본다.
# 아무도 안 보고 있으면 다음에 그 회의록을 여는 사람이 굴린다.
조용해질때까지 = dt.timedelta(
    minutes=float(os.environ.get("DCB_SUGGEST_QUIET_MIN", "3")))


def 분석_걸어둔다(background: BackgroundTasks, meeting: Meeting, db: Session,
             *, 지금: bool = False) -> None:
    """다시 부를 이유가 있으면 **기다렸다가** 부른다.

    `지금=True` 는 사람이 `지금 읽기` 를 눌렀을 때다 — 기다리지 않는다.
    기다리는 길만 있으면 "당장 보고 싶은데 3분을 기다려야" 한다.
    """
    if meeting.retreat_id is None:
        return
    if not 다시_읽어야_하나(meeting):
        return
    if not 지금:
        meeting.suggest_state = "기다림"
        meeting.suggest_due_at = dt.datetime.now() + 조용해질때까지
        db.commit()
        return
    meeting.suggest_state = "도는중"
    meeting.suggest_due_at = None
    db.commit()
    background.add_task(분석_한번, meeting.id)


def 때가_됐나(meeting: Meeting) -> bool:
    """기다리던 것이 이제 돌 때가 됐는가."""
    return (meeting.suggest_state == "기다림"
            and meeting.suggest_due_at is not None
            and dt.datetime.now() >= meeting.suggest_due_at)


@router.post("/{meeting_id}/suggestions/rerun")
def rerun_suggestions(
    meeting_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """**다시 시도.** 실패했을 때 사람이 누를 자리가 화면에 있어야 한다 —
    없으면 본문을 억지로 고쳐 저장하는 수밖에 없다."""
    meeting = _owned(db, meeting_id, retreat)
    meeting.suggest_hash = None
    # **누른 사람은 기다리려고 누른 것이 아니다** — 바로 돌린다
    분석_걸어둔다(background, meeting, db, 지금=True)
    return {"ok": True}


@router.get("/{meeting_id}/suggestions")
def meeting_suggestions(
    meeting_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """쌓아 둔 제안을 낸다. 아직 없으면 그 자리에서 걸어 두고 '도는 중' 을 답한다.

    **실패해도 화면은 살아 있어야 한다** (4-10 조건 8) — 여기서 터지면
    회의록 본문까지 못 읽게 된다.

    **비어 있는 것이 세 가지 뜻을 갖지 않게 한다.** '아직 안 끝났다' ·
    '낼 것이 없다'(조건 4의 정상) · '실패했다' 는 사람이 할 일이 전부
    다르다. `state` 로 나눠 보낸다.
    """
    meeting = _owned(db, meeting_id, retreat)

    # 사람 평가가 든 회의록인가 (6단계). **계산이라 API 와 무관하다** —
    # 키가 없어도, 분석이 실패해도 이 표시는 뜬다
    try:
        from app.domain.meeting_import import people_notes

        평가줄 = people_notes(meeting.body or "")
    except Exception:                       # noqa: BLE001
        평가줄 = []

    # **실패는 저절로 다시 돌리지 않는다.** 죽은 API 를 3초마다 두드리면
    # 값만 나가고 화면은 그대로다. 다시 시도는 사람이 누른다 (18번).
    if 때가_됐나(meeting):
        # 잠잠해졌다 — 이제 돈다. **시간을 재는 것은 화면이다** (위 설명)
        meeting.suggest_state = "도는중"
        meeting.suggest_due_at = None
        db.commit()
        background.add_task(분석_한번, meeting.id)
    # **이미 돌고 있으면 또 걸지 않는다.** 도는 동안에는 지문이 아직 없어서
    # "다시 읽어야 한다" 가 참인데, 그때 거는 순간 `도는중` 이 `기다림` 으로
    # 덮여 **지금 읽기를 누른 사람이 3분을 더 기다린다** (브라우저에서 그랬다).
    elif (meeting.suggest_state or "없음") not in ("실패", "기다림", "도는중") \
            and 다시_읽어야_하나(meeting):
        분석_걸어둔다(background, meeting, db)

    방식, _, 말 = (meeting.suggest_note or "").partition("|")
    if not 말:
        방식, 말 = "", 방식

    것들 = []
    if meeting.suggest_state == "됨" and meeting.suggest_json:
        try:
            것들 = json.loads(meeting.suggest_json) or []
        except Exception:                   # noqa: BLE001
            것들 = []

    # **이미 그 회의록에서 온 논의가 있으면 말한다.** 같은 것을 두 번 남기게
    # 두지 않는다 — 두 번 남으면 어느 것이 맞는지 알 수 없고, 지우는 길은
    # 그 업무의 논의 탭뿐이라 되돌리는 값이 비싸다.
    날 = meeting.meeting_date.isoformat() if meeting.meeting_date else "날짜 없음"
    표 = f"[회의록 {날}"
    이미 = {
        e.run_id
        for e in db.scalars(
            select(DiscussionEntry).where(DiscussionEntry.body.like(표 + "%")))
        if f"· {meeting.title}]" in (e.body or "")
    }
    남을것 = discussion_body(meeting)
    어디 = f"{날} 회의록"

    def 하자는말(x: dict) -> str:
        """**무엇을 하자는 것인지.** 왜 골랐는지가 아니라."""
        if x.get("kind") == "discussion":
            return f"이 회의 내용을 「{x.get('run_title')}」 의 논의로 남깁니다"
        if x.get("kind") == "new":
            말 = (x.get("title") or x.get("text") or "").split("— ", 1)[-1]
            # **화면에서만** 형광펜 표시를 뗀다. 본문에는 그대로 남고
            # 고르는 것도 그대로다 — 하려는 일을 읽는 데 방해만 된다
            for 표시 in ("⟨형광펜⟩", "⟨빨간형광펜⟩"):
                말 = 말.replace(표시, "")
            return 말.strip()
        return x.get("text") or ""

    항목 = []
    for x in 것들:
        run_id = x.get("run_id")
        항목.append({
            "kind": x.get("kind"),
            # 하려는 일이 먼저다. 화면이 이것을 크게 그린다
            "action": 하자는말(x),
            "text": x.get("text"),
            "why": x.get("why"),
            "run_id": run_id,
            "run_title": x.get("run_title"),
            "evidence": x.get("evidence") or [],
            "from": 어디,
            # 결정사항은 **회의록의 줄 그대로** 보여준다 (4단계)
            "quote": x.get("quote"),
            "parent_title": x.get("parent_title"),
            "department": x.get("department"),
            # 누르기 전에 볼 수 있어야 한다
            "preview": 남을것 if x.get("kind") == "discussion" else None,
            "already": bool(run_id and run_id in 이미),
        })

    return {
        "meeting": 어디,
        "state": meeting.suggest_state or "도는중",
        "how": 방식,                        # '문장' | '낱말' | ''
        "note": 말,
        "cost": meeting.suggest_cost or 0.0,
        "tokens": meeting.suggest_tokens or "",
        # 언제쯤 도는지 화면이 말해 준다 — 기다리는 줄 모르면 고장으로 읽힌다
        "wait_sec": (max(0, int((meeting.suggest_due_at - dt.datetime.now())
                                .total_seconds()))
                     if meeting.suggest_state == "기다림" and meeting.suggest_due_at
                     else 0),
        "people_notes": 평가줄[:8],
        "can_edit": not perm.is_readonly(user.role),
        "items": 항목,
        "failed": (meeting.suggest_state == "실패"),
    }


class SuggestionPick(BaseModel):
    run_id: int


@router.post("/{meeting_id}/suggestions/apply")
def apply_suggestion(
    meeting_id: int,
    payload: SuggestionPick,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """고른 제안 하나를 그 업무의 논의로 남긴다.

    **출처가 남는다.** 논의 본문 첫 줄에 어느 회의록에서 온 것인지 적고,
    `ActivityLog` 에 `actor_type='claude'` 로 기록한다 — 나중에 골라 낼 수
    있어야 한다 (옮기기의 `--undo` 와 같은 이유).
    """
    meeting = _owned(db, meeting_id, retreat)
    run = db.get(TaskRun, payload.run_id)
    if run is None or run.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다.")

    방식, _, _말 = (meeting.suggest_note or "").partition("|")
    if not _말:
        방식 = ""
    entry = DiscussionEntry(
        run_id=run.id,
        authored_at=meeting.meeting_date or dt.date.today(),
        # **미리보기와 같은 함수**를 쓴다. 두 벌이면 보여준 것과 남는 것이 갈린다
        body=discussion_body(meeting),
        author_id=user.id,
        author_name=user.name,
    )
    db.add(entry)
    db.flush()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회의록_제안_반영",
        target_type="discussion_entry",
        target_id=entry.id,
        # **어떤 방식으로 고른 제안이었는지 남긴다.** 낱말로 물러선 것과
        # 문장을 읽고 고른 것이 둘 다 `actor_type='claude'` 라, 이것이
        # 없으면 나중에 구별되지 않는다 — 성적을 견줄 때 그 구별이 전부다
        summary=f"{meeting.title} → {run.library.title} ({방식 or '알 수 없음'})",
        after_value={"meeting_id": meeting.id, "run_id": run.id,
                     "고른방식": 방식 or "알 수 없음"},
        actor_type="claude",
    )
    db.commit()
    return {"ok": True, "entry_id": entry.id, "run_title": run.library.title}
