"""봉사자 시간표 (CLAUDE.md 5-8) — **표를 만드는 곳은 여기 하나다.**

화면(HTML)과 내려받기(xlsx)가 **같은 함수에서 나온 같은 구조**를 그린다.
따로 만들면 반드시 어긋난다 — 이 프로젝트에서 가장 자주 고쳐 온 문제가
"같은 것이 두 곳에 있는 것" 이다. 그래서 판정·색·병합을 화면이나 xlsx 쪽에서
다시 계산하지 않는다. 저쪽은 여기서 나온 칸을 놓기만 한다.

원래 쓰던 구글시트의 '봉사자 시간표' 모양을 그대로 옮긴 것이라, 가로로 길고
시각 열이 양쪽 끝에 하나씩 있다.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy.orm import Session

from app.domain import live as live_domain
from app.models import PROGRAM_PARTS, TEAM_WORDS, Program, Retreat

# ── 세로축 ───────────────────────────────────────────────────────────
#
# 06:00 부터 다음날 01:00 까지. **한 시각이 두 줄**(30분 눈금)이라 06:00 은
# 두 줄을 차지한다. 자정을 넘긴 시각은 24 를 더해 아래에 둔다 —
# 그러지 않으면 `00:00 광고` 가 `06:00` 위에 서서 하루가 통째로 뒤집힌다.
START_HOUR = 6
END_HOUR = 25                     # 25 = 다음날 01:00
ROWS_PER_HOUR = 2
BODY_ROWS = (END_HOUR - START_HOUR + 1) * ROWS_PER_HOUR
HEADER_ROWS = 2

# ── 칸의 크기 ────────────────────────────────────────────────────────
#
# **한 줄의 높이는 어디서나 같습니다.** 시간표는 세로가 시간이어야 읽히는데,
# 내용이 많은 칸이 줄을 밀어내면 왼쪽 시각 눈금이 오른쪽 내용과 어긋납니다 —
# 06:00 은 한 줄, 11:00 은 세 줄 높이가 되어 13:00 옆에 14:00·15:00 이 몰립니다.
# 그래서 높이를 고정하고, 글이 넘치면 **칸을 늘리는 대신 글자를 줄입니다.**
#
# **가로세로 비율은 원본 시트에서 읽은 값입니다.** 세로가 시간인 표라
# 비율 자체가 뜻을 가집니다 — 납작하면 같은 한 시간이 좁아 보여 일정이
# 실제보다 촘촘하게 느껴집니다. **여기 적은 네 값이 화면(px)과 파일(엑셀
# 단위)의 유일한 출처입니다** — 두 곳에서 따로 정하면 반드시 어긋납니다.
SRC_TIME_COL = 8.43               # 시각 열 (엑셀 열 너비 단위)
SRC_COL_MAIN = 11.63              # 내용 칸의 왼쪽 절반
SRC_COL_SIDE = 8.43               # 오른쪽 절반 (나란히 도는 것이 서는 자리)
SRC_ROW_PT = 28.5                 # 자료 한 줄 (포인트)

SRC_CONTENT_COL = SRC_COL_MAIN + SRC_COL_SIDE          # 20.06 — 한 칸의 너비
SRC_HOUR_PT = SRC_ROW_PT * ROWS_PER_HOUR               # 57.0 — 한 시각의 높이

# 한 시각의 높이 : 한 칸의 너비 = 57 : 20.06 ≈ 2.84.
# **두 수의 단위가 다릅니다** — 포인트와 엑셀 열 너비 단위입니다. 그래서 이
# 2.84 는 화면에서 보이는 세로/가로 비가 아니라 **원본이 적어 둔 두 값의 비**
# 입니다. 실제로 보이는 비율은 아래 두 환산을 거쳐 나옵니다(0.5 쯤).
# 어느 쪽이든 **원본과 같아지는 것이 목적**이라 이 한 값에서 전부 끌어옵니다.
HOUR_TO_WIDTH = SRC_HOUR_PT / SRC_CONTENT_COL

# 엑셀의 두 단위를 화면 px 로 옮기는 환산 (표준값)
EXCEL_COL_UNIT_PX = 7.0           # 열 너비 1 단위
EXCEL_COL_PAD_PX = 5.0            # 열마다 붙는 여백
PT_TO_PX = 96 / 72


def _width_px(units: float) -> int:
    """엑셀 열 너비 → 화면 px."""
    return round(units * EXCEL_COL_UNIT_PX + EXCEL_COL_PAD_PX)


ROW_HEIGHT_PX = round(SRC_ROW_PT * PT_TO_PX)           # 38
TIME_COL_PX = _width_px(SRC_TIME_COL)                  # 64
COL_MAIN_PX = _width_px(SRC_COL_MAIN)                  # 86
COL_SIDE_PX = _width_px(SRC_COL_SIDE)                  # 64
COL_WIDTH_PX = COL_MAIN_PX + COL_SIDE_PX               # 150 — 한 칸 전체

CELL_PAD_PX = 12                  # 좌우 여백 + 테두리

# ── 글자 크기 ────────────────────────────────────────────────────────
#
# **칸 크기와 글자 크기는 같이 정해야 합니다.** 하나만 바꾸면 어긋납니다 —
# 실제로 칸 비율만 원본에 맞추고 글자를 그대로 두었더니 여백만 넓어져서
# 내용이 적은 날(폐회)이 휑해 보였습니다. 그래서 글자도 **줄 높이에서**
# 끌어옵니다. 줄 높이가 바뀌면 글자가 따라 바뀝니다.
#
# 원본은 10pt : 28.5pt ≈ 0.35 입니다. 우리는 그보다 조금 큽니다 — 원본은
# 한 줄이 한 칸이지만 우리는 여러 줄에 걸친 칸이 많고 글이 위에 붙으므로,
# 같은 비율로는 아래가 비어 보입니다.
FONT_TO_ROW = 0.42
HEAD_FONT_SCALE = 1.10            # 머리줄과 시각 열은 본문보다 크고 굵게
DENSE_FONT_SCALE = 0.82           # 넘치는 칸만 작게 — 기본이 커진 만큼 함께 커진다
LINE_SCALE = 1.32
DENSE_LINE_SCALE = 1.28

BODY_FONT_PT = round(SRC_ROW_PT * FONT_TO_ROW, 1)            # 12.0
HEAD_FONT_PT = round(BODY_FONT_PT * HEAD_FONT_SCALE, 1)      # 13.2
DENSE_FONT_PT = round(BODY_FONT_PT * DENSE_FONT_SCALE, 1)    # 9.8

BODY_FONT_PX = round(BODY_FONT_PT * PT_TO_PX)                # 16
HEAD_FONT_PX = round(HEAD_FONT_PT * PT_TO_PX)                # 18
DENSE_FONT_PX = round(DENSE_FONT_PT * PT_TO_PX)              # 13
LINE_PX = round(BODY_FONT_PX * LINE_SCALE)                   # 21
DENSE_LINE_PX = round(DENSE_FONT_PX * DENSE_LINE_SCALE)      # 17
HEAD_ROW_PX = round(HEAD_FONT_PX * 1.7)                      # 머리 한 줄의 높이


def cell_width_px(col: int, colspan: int) -> int:
    """칸 하나의 가로 px. 좌우 절반의 너비가 다르므로 어느 쪽인지를 받는다."""
    if colspan >= 2:
        return COL_WIDTH_PX
    return COL_SIDE_PX if col else COL_MAIN_PX


# 한글은 글자 폭이 글자 크기와 비슷하고 영문·숫자는 그 절반쯤이다.
# 글자 수로 세면 `Belong FM 준비 (13:00)` 같은 줄이 실제보다 길게 잡힌다.
NARROW_CHAR_RATIO = 0.52          # 한글 한 글자 폭 대비 영문·숫자

# 개회일 전체일정의 앞쪽 빈 구간에 적는 말 (5-8)
NOTE_BEFORE_ARRIVAL = "참가자 등록 전"

# ── 색 (원본 파일에서 읽은 값) ────────────────────────────────────────
FILL_DAY = "D9D9D9"               # 일자 머리
FILL_STAFF_HEAD = "FFF2CC"        # 봉사자 칸 머리
FILL_ALL_HEAD = "D9EAD3"          # 전체일정 칸 머리
FILL_ALL = "D9EAD3"               # 전체일정 내용
FILL_STAFF = "FFF2CC"             # 봉사자 내용 (공통)
FILL_NONE = None                  # 빈 칸

# 봉사팀 파트별 색. **목록을 코드에 박지 않고 파트 순서대로 배정한다** —
# 파트가 늘면 색도 늘어야 한다. 헤브론이 첫째라 CFE2F3, 코람데오가 둘째라 FCE5CD.
TEAM_PART_FILLS = ("CFE2F3", "FCE5CD", "E6D7F2", "D9EAD3", "FFF2CC")


def team_parts() -> list[str]:
    """봉사팀 파트를 `PROGRAM_PARTS` 에 적힌 순서대로."""
    return [p for p in PROGRAM_PARTS if p in live_domain.TEAM_PARTS]


def fill_for_part(part: str) -> str:
    """그 파트의 색. 목록에 없으면 봉사자 공통색으로 떨어진다."""
    order = team_parts()
    if part in order:
        return TEAM_PART_FILLS[order.index(part) % len(TEAM_PART_FILLS)]
    return FILL_STAFF


# ── 담당 표기 ────────────────────────────────────────────────────


def generic_words() -> frozenset[str]:
    """`총무팀` `전체` 처럼 **특정인을 가리키지 않는** 말.

    `TEAM_WORDS` 에서 봉사팀 이름만 빼고 나머지입니다 — 목록을 따로 적으면
    파트가 늘 때 한쪽만 고쳐집니다.
    """
    return frozenset(TEAM_WORDS) - set(team_parts())


_SPLIT = re.compile(r"\s*[·,/]\s*")


def who_of(raw: str | None) -> str:
    """담당 표기에서 **봉사팀에게 쓸모 있는 것만** 남깁니다 (5-8).

    봉사팀에게 보내는 표라 `아침식사 (총무팀)` 의 괄호는 알 필요가 없습니다.
    거의 모든 칸에 붙어서 정작 사람 이름이 묻힙니다. 사람 이름과 봉사팀
    이름만 남기고, 남는 것이 없으면 괄호를 아예 내지 않습니다.

    **버릴 것이 없으면 원문을 그대로 돌려줍니다** — 구분자를 다시 짜맞추면
    `하람·나윤` 이 `하람 · 나윤` 으로 바뀌어, 고칠 이유가 없는 표기가 흔들립니다.
    """
    if not raw:
        return ""
    generic = generic_words()
    pieces = [p for p in _SPLIT.split(raw.strip()) if p]
    kept = [p for p in pieces if p not in generic]
    if len(kept) == len(pieces):
        return raw.strip()
    return " · ".join(kept)


def _detail(who: str | None, place: str | None) -> str:
    """괄호에 들어갈 말. **장소는 그대로 냅니다** — 봉사팀에게 쓸모가 있습니다."""
    parts = [x for x in (who_of(who), (place or "").strip()) if x]
    return " · ".join(dict.fromkeys(parts))


# ── 같은 말이 두 번 나오지 않게 ──────────────────────────────────


def _squash(text: str) -> str:
    """띄어쓰기와 구분자를 지운 비교용 문자열."""
    return re.sub(r"[\s·,/&]+", "", text or "")


def same_thing(program_name: str, item_text: str) -> bool:
    """프로그램과 그 프로그램에 붙은 봉사팀 항목이 **사실상 같은 말인가.**

    이름만으로 견주지 않고 **한쪽이 다른 쪽 안에 들어 있는지**로 봅니다 —
    `음향 및 무대설치` ⊂ `음향 및 무대설치 (3.5h)`, `하차` ⊂ `본당 도착 · 하차`.
    """
    a, b = _squash(program_name), _squash(item_text)
    if not a or not b:
        return False
    return a in b or b in a


def _merge_pair(program: dict, item: dict) -> dict:
    """같은 말인 둘을 **하나로** 만듭니다.

    **항목 쪽에 괄호 정보(`3.5h` 등)가 더 있으면 그쪽을 씁니다.** 없으면
    프로그램 쪽을 남깁니다 — 애매할 때 빠지는 것보다 겹치는 것이 더 거슬리므로
    한쪽을 반드시 고르되, 기본은 원래 시간표의 이름인 프로그램 쪽입니다.

    **버리는 쪽의 담당은 잃지 않습니다** — `하차 (헤브론)` 를 버리고
    `본당 도착 · 하차 (전체)` 만 남기면 헤브론이 관련된 사실이 사라집니다.
    """
    item_has_note = "(" in item["title"] and "(" not in program["title"]
    keep = item if item_has_note else program
    merged = dict(keep)
    merged["detail"] = " · ".join(
        dict.fromkeys(x for x in (program["detail"], item["detail"]) if x)
    )
    # 색은 봉사팀 항목 쪽을 따릅니다 — 어느 팀 일인지가 이 표의 값입니다
    merged["fill"] = item["fill"]
    return merged


# ── 시각 ─────────────────────────────────────────────────────────────


def minutes_of(hhmm: str | None) -> int | None:
    try:
        hour, _, minute = (hhmm or "").partition(":")
        return int(hour) * 60 + int(minute)
    except ValueError:
        return None


def row_of(hhmm: str | None) -> int | None:
    """시각 → 줄 번호. **문자열로 정렬하지 않는다** (5-8 함정).

    자정을 넘긴 시각(00:00~05:59)은 하루의 끝이므로 24시간을 더해 아래로 보낸다.
    """
    minute = minutes_of(hhmm)
    if minute is None:
        return None
    if minute < START_HOUR * 60:
        minute += 24 * 60
    index = (minute - START_HOUR * 60) // 30
    if index < 0 or index >= BODY_ROWS:
        return None
    return index


def row_label(index: int) -> str | None:
    """그 줄의 시각 표시. 정각 줄에만 붙인다."""
    if index % ROWS_PER_HOUR:
        return None
    hour = START_HOUR + index // ROWS_PER_HOUR
    return f"{hour % 24:02d}:00"


# ── 표 만들기 ────────────────────────────────────────────────────────


def _entries_for(day_programs: list[Program]) -> tuple[list[dict], list[dict]]:
    """(전체일정 칸에 들어갈 것, 봉사자 칸에 들어갈 것).

    **`ops` 프로그램도 총무팀 개인 항목도 넣지 않는다.** 이것이 이 표의 이유다 —
    봉사팀이 보는 것은 "우리가 언제 모여 무엇을 하나" 이지 총무팀의 실행 목록이 아니다.
    """
    everyone: list[dict] = []
    staff: list[dict] = []

    for program in day_programs:
        start = row_of(program.start_time)
        if start is None:
            continue

        # 봉사팀 파트 항목 — 총무팀 파트 항목은 넣지 않는다
        items = [
            {
                "row": start,
                "end_row": None,
                "time": program.start_time,
                "title": item.text,
                "detail": _detail(item.assignee_name, None),
                "parallel": False,
                "fill": fill_for_part(item.part_key),
                "part": item.part_key,
            }
            for item in program.items
            if item.part_key in live_domain.TEAM_PARTS
        ]

        if program.track_key != "main":
            # ops 프로그램은 넣지 않는다. 다만 거기 달린 봉사팀 항목은 그 팀의
            # 일이므로 남긴다 — 프로그램이 없으니 겹칠 일도 없다
            staff.extend(items)
            continue

        entry = {
            "row": start,
            "end_row": row_of(program.end_time) if program.end_time else None,
            "time": program.start_time,
            "title": program.name,
            "detail": _detail(program.host, program.place),
            "parallel": program.is_parallel,
            "fill": FILL_ALL if program.audience_key == "all" else FILL_STAFF,
        }

        if program.audience_key == "all":
            # 프로그램은 전체일정 칸, 항목은 봉사자 칸 — 서로 다른 칸이라
            # 같은 말이어도 나란히 찍히지 않는다. 합치지 않는다
            everyone.append(entry)
            staff.extend(items)
            continue

        # 둘 다 봉사자 칸에 들어간다 — 같은 말이면 한 번만 낸다
        rest = []
        for item in items:
            if same_thing(entry["title"], item["title"]):
                entry = _merge_pair(entry, item)
            else:
                rest.append(item)
        staff.append(entry)
        staff.extend(rest)

    return everyone, staff


def _place(entries: list[dict]) -> list[dict]:
    """한 칸(두 열)에 놓을 칸들을 만든다.

    · **같은 줄에서 시작하는 것은 한 칸에 합친다** (5-8 함정). 그냥 넣으면
      나중 것이 앞엣것을 덮어쓴다 — 2일차 00:00 의 광고와 야식이 그렇다
    · **나란히 도는 것을 시각으로 추측하지 않는다** (5-8 함정).
      `parallel` 로 적힌 것만 오른쪽 열로 뺀다
    """
    left_groups: dict[int, list[dict]] = {}
    right_groups: dict[int, list[dict]] = {}
    for entry in entries:
        target = right_groups if entry["parallel"] else left_groups
        target.setdefault(entry["row"], []).append(entry)

    def spans(groups: dict[int, list[dict]]) -> list[dict]:
        rows = sorted(groups)
        out = []
        for i, row in enumerate(rows):
            group = groups[row]
            following = rows[i + 1] if i + 1 < len(rows) else BODY_ROWS
            # end_time 이 있으면 거기까지, 없으면 다음 것 시작 전까지
            ends = [e["end_row"] for e in group if e["end_row"] is not None]
            end = min(ends) if ends else following
            end = max(row + 1, min(end, following))
            out.append({"row": row, "end": end, "entries": group})
        return out

    left, right = spans(left_groups), spans(right_groups)

    # 왼쪽이 반 칸이 되는 구간 — 오른쪽에 무언가가 겹쳐 도는 동안
    def overlaps_right(block: dict) -> bool:
        return any(
            block["row"] < r["end"] and r["row"] < block["end"] for r in right
        )

    cells = []
    for block in left:
        cells.append({
            "row": block["row"], "rowspan": block["end"] - block["row"],
            "col": 0, "colspan": 1 if overlaps_right(block) else 2,
            "entries": block["entries"],
        })
    for block in right:
        cells.append({
            "row": block["row"], "rowspan": block["end"] - block["row"],
            "col": 1, "colspan": 1,
            "entries": block["entries"],
        })
    return cells


def _fill_of(entries: list[dict]) -> str | None:
    """한 칸의 색.

    **섞인 칸은 어느 팀의 것도 아니다.** 프로그램과 봉사팀 항목이 같은 시각에
    놓여 한 칸에 합쳐지면 첫째 것의 색을 쓸 수 없다 — 첫째가 무엇인지에 따라
    같은 칸이 파랬다 노랬다 한다. 색이 갈리면 봉사자 공통색으로 떨어뜨린다.
    """
    colors = {entry["fill"] for entry in entries}
    return colors.pop() if len(colors) == 1 else FILL_STAFF


def _text_of(entries: list[dict]) -> str:
    """한 칸에 여럿이 들어가면 줄바꿈으로 잇는다."""
    lines = []
    for entry in entries:
        line = entry["title"]
        if entry["detail"]:
            line += f" ({entry['detail']})"
        lines.append(line)
    return "\n".join(lines)


def _text_width(piece: str, size_px: float) -> float:
    """글 한 줄이 차지하는 가로 길이(px).

    한글은 글자 폭이 글자 크기와 비슷하고 영문·숫자는 그 절반쯤이다.
    **글자 크기에서 계산한다** — 크기를 키우면 줄 수도 따라 늘어야 한다.
    """
    narrow = size_px * NARROW_CHAR_RATIO
    return sum(size_px if ord(ch) > 0x2000 else narrow for ch in piece)


def wrapped_lines(text: str, colspan: int, *, col: int = 0,
                  dense: bool = False) -> int:
    """이 글이 그 폭에서 몇 줄이 되는가."""
    if not text:
        return 0
    usable = cell_width_px(col, colspan) - CELL_PAD_PX
    size = DENSE_FONT_PX if dense else BODY_FONT_PX
    return sum(
        max(1, -(-_text_width(piece, size) // usable))
        for piece in text.split("\n")
    )


def dense_of(text: str, rowspan: int, colspan: int, col: int = 0) -> bool:
    """이 칸의 글이 **정해진 높이에 안 들어가는가.**

    줄 높이는 고정이므로(`ROW_HEIGHT_PX`) 넘치는 것은 칸을 늘려서가 아니라
    **글자를 줄여서** 담는다. 화면과 파일이 같은 판단을 쓰도록 여기서 센다.
    """
    room = rowspan * ROW_HEIGHT_PX
    return wrapped_lines(text, colspan, col=col) * LINE_PX > room


def build(db: Session, retreat: Retreat) -> dict:
    """봉사자 시간표 한 장. **화면과 xlsx 가 이것을 같이 쓴다.**"""
    programs = live_domain.load_programs(db, retreat)
    dates = live_domain.day_dates(retreat)
    day_names = live_domain.day_names(retreat, programs)

    by_day: dict[str, list[Program]] = {name: [] for name in day_names}
    for program in programs:
        by_day.setdefault(program.day, []).append(program)

    # ── 열 짜기 ──
    columns: list[dict] = [
        {"kind": "time", "day": None, "band": None,
         "width": SRC_TIME_COL, "width_px": TIME_COL_PX}
    ]
    bands: list[dict] = []
    for name in day_names:
        rows_for_day = by_day.get(name, [])
        everyone, staff = _entries_for(rows_for_day)
        # **전체일정이 하나도 없는 날은 그 칸 자체를 만들지 않는다** —
        # 빈 칸을 두면 "왜 비었지" 를 묻게 된다 (선발대가 그렇다)
        day_bands = [("staff", staff)]
        if everyone:
            day_bands.append(("all", everyone))

        for band, entries in day_bands:
            start_col = len(columns)
            columns.append({"kind": "content", "day": name, "band": band,
                            "half": 0, "width": SRC_COL_MAIN,
                            "width_px": COL_MAIN_PX})
            columns.append({"kind": "content", "day": name, "band": band,
                            "half": 1, "width": SRC_COL_SIDE,
                            "width_px": COL_SIDE_PX})
            bands.append({
                "day": name, "band": band, "col": start_col, "entries": entries,
            })
    columns.append({"kind": "time", "day": None, "band": None,
                    "width": SRC_TIME_COL, "width_px": TIME_COL_PX})
    time_right = len(columns) - 1

    cells: list[dict] = []

    # ── 머리 두 줄 ──
    for col in (0, time_right):
        cells.append({
            "row": 0, "col": col, "rowspan": HEADER_ROWS, "colspan": 1,
            "text": "시각", "fill": FILL_DAY, "kind": "head", "align": "center",
            "dense": False,
        })
    seen_day: dict[str, list[int]] = {}
    for band in bands:
        seen_day.setdefault(band["day"], []).append(band["col"])
    for name, cols in seen_day.items():
        first = min(cols)
        width = (max(cols) + 2) - first
        date = dates.get(name)
        label = f"{name}" + (f"  {live_domain.label_of(name, date)}" if date else "")
        cells.append({
            "row": 0, "col": first, "rowspan": 1, "colspan": width,
            "text": label, "fill": FILL_DAY, "kind": "head", "align": "center",
            "dense": False,
        })
    for band in bands:
        cells.append({
            "row": 1, "col": band["col"], "rowspan": 1, "colspan": 2,
            "text": "봉사자" if band["band"] == "staff" else "전체일정",
            "fill": FILL_STAFF_HEAD if band["band"] == "staff" else FILL_ALL_HEAD,
            "kind": "head", "align": "center", "dense": False,
        })

    # ── 시각 열 (한 시각이 두 줄이라 두 줄씩 묶는다) ──
    for index in range(0, BODY_ROWS, ROWS_PER_HOUR):
        for col in (0, time_right):
            cells.append({
                "row": HEADER_ROWS + index, "col": col,
                "rowspan": ROWS_PER_HOUR, "colspan": 1,
                "text": row_label(index) or "", "fill": FILL_NONE,
                "kind": "time", "align": "center", "dense": False,
            })

    # 참가자가 아직 오지 않은 구간을 알아보기 위해 개회일을 찾아 둔다
    opening = next(
        (name for name, date in dates.items() if date == retreat.start_date), None
    )

    # ── 내용 ──
    for band in bands:
        taken = [[False, False] for _ in range(BODY_ROWS)]
        placed = _place(band["entries"])

        # **개회일 전체일정의 앞쪽 빈 구간에 한 줄 적는다.** 참가자가 아직
        # 없어서 비어 있는 것이 맞는데, 그 큰 공백은 "뭔가 빠진 것" 처럼
        # 보인다. 칸을 채우려는 것이 아니라 **비어 있는 것이 정상임을
        # 말해 주는 것**이므로 색은 넣지 않는다.
        if band["band"] == "all" and band["day"] == opening:
            first = min((c["row"] for c in placed), default=BODY_ROWS)
            if first >= ROWS_PER_HOUR:
                for r in range(first):
                    taken[r][0] = taken[r][1] = True
                cells.append({
                    "row": HEADER_ROWS, "col": band["col"],
                    "rowspan": first, "colspan": 2,
                    "text": NOTE_BEFORE_ARRIVAL, "fill": FILL_NONE,
                    "kind": "note", "align": "center", "dense": False,
                    "day": band["day"], "band": band["band"],
                })

        for cell in placed:
            for r in range(cell["row"], cell["row"] + cell["rowspan"]):
                for c in range(cell["col"], cell["col"] + cell["colspan"]):
                    taken[r][c] = True
            entries = cell["entries"]
            text = _text_of(entries)
            cells.append({
                "row": HEADER_ROWS + cell["row"],
                "col": band["col"] + cell["col"],
                "rowspan": cell["rowspan"], "colspan": cell["colspan"],
                "text": text,
                "fill": _fill_of(entries),
                "kind": "body", "align": "left",
                "dense": dense_of(
                    text, cell["rowspan"], cell["colspan"], cell["col"]),
                "day": band["day"], "band": band["band"],
            })

        # **내용이 없는 칸도 시각 단위(2줄×2열)로 병합한다** —
        # 안 그러면 격자가 잘게 쪼개져 보인다.
        for index in range(0, BODY_ROWS, ROWS_PER_HOUR):
            block = [taken[index + k] for k in range(ROWS_PER_HOUR)]
            free_both = all(not row[0] and not row[1] for row in block)
            if free_both:
                cells.append({
                    "row": HEADER_ROWS + index, "col": band["col"],
                    "rowspan": ROWS_PER_HOUR, "colspan": 2,
                    "text": "", "fill": FILL_NONE, "kind": "empty", "align": "left",
                    "dense": False,
                })
                continue
            for c in (0, 1):
                if all(not row[c] for row in block):
                    cells.append({
                        "row": HEADER_ROWS + index, "col": band["col"] + c,
                        "rowspan": ROWS_PER_HOUR, "colspan": 1,
                        "text": "", "fill": FILL_NONE, "kind": "empty",
                        "align": "left", "dense": False,
                    })
                    continue
                # 반 칸만 비어 있는 줄은 한 줄씩 채운다
                for k in range(ROWS_PER_HOUR):
                    if not block[k][c]:
                        cells.append({
                            "row": HEADER_ROWS + index + k, "col": band["col"] + c,
                            "rowspan": 1, "colspan": 1, "text": "",
                            "fill": FILL_NONE, "kind": "empty", "align": "left",
                            "dense": False,
                        })

    cells.sort(key=lambda c: (c["row"], c["col"]))
    return {
        "retreat": retreat.name,
        "columns": columns,
        "cells": cells,
        "header_rows": HEADER_ROWS,
        "row_height": ROW_HEIGHT_PX,
        "row_height_pt": SRC_ROW_PT,
        # **글자 크기도 여기서 나갑니다.** CSS 나 xlsx 쪽에 적어 두면
        # 칸만 커지고 글자는 그대로인 상태가 또 생깁니다 (5-8)
        "font": {
            "body_px": BODY_FONT_PX, "body_pt": BODY_FONT_PT,
            "head_px": HEAD_FONT_PX, "head_pt": HEAD_FONT_PT,
            "dense_px": DENSE_FONT_PX, "dense_pt": DENSE_FONT_PT,
            "line_px": LINE_PX, "dense_line_px": DENSE_LINE_PX,
            "head_row_px": HEAD_ROW_PX,
        },
        "body_rows": BODY_ROWS,
        "total_rows": HEADER_ROWS + BODY_ROWS,
        "total_cols": len(columns),
        "time_cols": (0, time_right),
        # 일자 사이에만 굵은 선을 긋기 위해 경계 열을 알려준다
        "day_edges": sorted({min(cols) for cols in seen_day.values()}) + [time_right],
        "days": [
            {"name": name, "label": live_domain.label_of(name, dates.get(name)),
             "bands": [b["band"] for b in bands if b["day"] == name]}
            for name in day_names
        ],
    }


def check_merges(cells: list[dict]) -> list[str]:
    """병합이 겹치는 곳. **저장 전에 반드시 본다** (5-8).

    겹치면 엑셀이 "읽을 수 없는 내용이 있습니다" 를 띄우는데 openpyxl 은 아무
    말도 하지 않는다. 손상된 파일을 만들어 놓고 성공했다고 하면 안 된다.
    """
    owner: dict[tuple[int, int], str] = {}
    problems: list[str] = []
    for cell in cells:
        name = f"({cell['row']},{cell['col']}) {cell.get('text', '')[:16]!r}"
        for r in range(cell["row"], cell["row"] + cell["rowspan"]):
            for c in range(cell["col"], cell["col"] + cell["colspan"]):
                if (r, c) in owner:
                    problems.append(f"{r}행 {c}열이 겹칩니다 — {owner[(r, c)]} 와 {name}")
                else:
                    owner[(r, c)] = name
    return problems


def now_label(now: dt.datetime | None = None) -> str:
    """내려받은 시각. **벽시계 시각으로 적는다** — UTC 로 적으면 새벽에 하루 전이 된다."""
    return (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
