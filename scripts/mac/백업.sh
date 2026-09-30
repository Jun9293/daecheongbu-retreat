#!/bin/bash
# 맥의 매일 백업 — 윈도우 작업 「대청부 백업」(03:00)의 자리 (docs/맥-이전.md).
# launchd(com.daecheongbu.backup)가 새벽 3시에 부른다. 사람이 불러도 된다.
#
#   scripts/mac/백업.sh
#
# **하는 일은 scripts/backup.py 가 한다** — DB 는 VACUUM INTO(쓰는 중에도 일관된 사본),
# 행 수 · VAPID 키 · 업로드 zip 을 같은 날짜로 묶고, 성한 판 30 · 전체 10GB 를 넘는
# 것만 오래된 것부터 지운다(의심 판 · 지키는판 규칙 포함). 그 규칙을 여기 다시 적지
# 않는다 — 두 벌이면 한쪽만 고쳐진다. 이 파일은 **부르기 전에 볼 것**만 본다.
#
# 설정(.env · DCB_ENV_FILE — env.sh 로 읽는다)
#   DCB_BACKUP_DIR   백업 위치. 비면 <데이터>/backups. **절대 경로만**
#
# 끝나는 코드
#   0  백업함          1  backup.py 가 실패(까닭을 한 줄로 남김)
#   69 위치가 붙어 있지 않음(/Volumes/… 드라이브가 빠짐) 또는 venv 없음
#   73 위치에 쓸 수 없음       75 다른 백업이 도는 중      78 설정이 틀림
#
# **빠진 드라이브 자리에 폴더를 만들지 않는다.** /Volumes/이름 이 붙어 있지 않을 때
# 거기 mkdir 하면 내장 디스크에 폴더가 생겨 백업이 조용히 거기 쌓인다.
# **여러 번 불러도 안전하다** — 잠금으로 동시에 둘이 돌지 않고, 판 이름이 초 단위라
# 앞의 판을 덮지 않는다.

set -u
export PATH="/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/../.." && pwd -P)"

say() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] 백업: $*" >&2; }
die() { say "$2"; exit "$1"; }

# shellcheck source=env.sh
. "$HERE/env.sh"
ENV_FILE="${DCB_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  dcb_load_env "$ENV_FILE"
elif [ -n "${DCB_ENV_FILE:-}" ]; then
  die 78 "DCB_ENV_FILE 이 가리키는 파일이 없습니다: $ENV_FILE"
fi

DATA="${DCB_DATA_DIR:-$ROOT/data}"
BK="${DCB_BACKUP_DIR:-$DATA/backups}"
case "$BK" in /*) ;; *) die 78 "DCB_BACKUP_DIR 은 절대 경로여야 합니다" ;; esac

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || die 69 "가상환경이 없습니다: $ROOT/.venv"

# ── 위치가 붙어 있나 ─────────────────────────────────────────────────
# /Volumes/이름/… 이면 /Volumes/이름 이 **실제로 붙은 자리**여야 한다 — 장치 번호가
# /Volumes 와 달라야 한다(빠진 드라이브는 자리가 없거나 내장 디스크의 빈 폴더다).
case "$BK" in
  /Volumes/*)
    vol="/Volumes/$(printf '%s' "${BK#/Volumes/}" | cut -d/ -f1)"
    if [ ! -d "$vol" ] || [ "$(stat -L -f '%d' "$vol" 2>/dev/null)" = "$(stat -L -f '%d' /Volumes)" ]; then
      die 69 "백업 위치가 붙어 있지 않습니다: $vol — 드라이브를 연결한 뒤 다시 부르세요"
    fi
    ;;
esac

if [ ! -d "$BK" ]; then
  mkdir -p "$BK" 2>/dev/null || die 73 "백업 위치를 만들 수 없습니다: $BK"
fi
probe="$(mktemp "$BK/.쓰기시험.XXXXXX" 2>/dev/null)" || die 73 "백업 위치에 쓸 수 없습니다: $BK"
rm -f "$probe"

# ── 잠금 — 동시에 둘이 돌지 않게 ────────────────────────────────────
LOCK="$BK/.backup.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  other="$(cat "$LOCK/pid" 2>/dev/null || echo '')"
  if [ -n "$other" ] && kill -0 "$other" 2>/dev/null; then
    die 75 "다른 백업이 도는 중입니다(pid $other) — 이번은 건너뜁니다"
  fi
  say "지난 잠금이 남아 있어(주인 없음) 걷고 이어 갑니다"
  rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null || die 75 "잠금을 잡지 못했습니다: $LOCK"
fi
echo $$ >"$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

# ── 부른다 ────────────────────────────────────────────────────────────
cd "$ROOT" || die 69 "저장소 폴더로 못 갑니다: $ROOT"
export DCB_BACKUP_DIR="$BK" DCB_DATA_DIR="$DATA"
say "시작 → $BK"
# 줄마다 시각을 붙여 남긴다. 끝 코드는 파이썬 쪽 것을 쓴다
"$PY" scripts/backup.py 2>&1 | while IFS= read -r line; do echo "[$(date '+%Y-%m-%d %H:%M:%S')] 백업: $line"; done
rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then say "backup.py 가 $rc 로 끝났습니다 — 위 줄에 까닭이 있습니다"; exit 1; fi
say "끝"
