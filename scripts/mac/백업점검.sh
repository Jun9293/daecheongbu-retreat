#!/bin/bash
# 백업이 싱싱한가 — **읽기만 한다** (docs/맥-이전.md). 하루 한 번 launchd(com.daecheongbu.backupcheck)가 부른다.
#
#   scripts/mac/백업점검.sh
#
# 마지막 **성한 판**(빈 판은 안 센다 — 판정은 scripts/backup.py 의 `신선도` 하나)의 나이가
# 기준을 넘으면 한 줄로 말하고 1 로 끝난다. **백업이 안 돌면 백업은 아무 말도 못 한다** —
# 기계가 꺼져 새벽 3시를 건너뛰었거나 드라이브가 빠져 며칠째 안 떴을 때를 바깥에서 본다.
#
# 설정(.env · DCB_ENV_FILE — env.sh 로 읽는다)
#   DCB_BACKUP_DIR              백업 위치(백업.sh 와 같은 값). 비면 <데이터>/backups
#   DCB_BACKUP_MAX_AGE_HOURS    기준(시간). 기본 30 — 하루 한 번 뜨므로 하루 + 여유
#
# 끝나는 코드  0 싱싱함 · 1 오래됨/판 없음/폴더 없음 · 69 위치가 붙어 있지 않음 · 78 설정이 틀림
# **아무것도 만들지 않는다** — 폴더도, 옆 파일도, 알림도(사람에게 닿게 하는 것은 아직 없다 · 맥-이전 9장).

set -u
export PATH="/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/../.." && pwd -P)"

say() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] 백업점검: $*" >&2; }

# shellcheck source=env.sh
. "$HERE/env.sh"
ENV_FILE="${DCB_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  dcb_load_env "$ENV_FILE"
elif [ -n "${DCB_ENV_FILE:-}" ]; then
  say "DCB_ENV_FILE 이 가리키는 파일이 없습니다: $ENV_FILE"; exit 78
fi

DATA="${DCB_DATA_DIR:-$ROOT/data}"
AGE="${DCB_BACKUP_MAX_AGE_HOURS:-30}"
if ! [[ "$AGE" =~ ^[0-9]+([.][0-9]+)?$ ]] || ! awk -v a="$AGE" 'BEGIN { exit !(a > 0) }'; then
  say "DCB_BACKUP_MAX_AGE_HOURS 는 0 보다 큰 숫자여야 합니다"; exit 78
fi

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || { say "가상환경이 없습니다: $ROOT/.venv"; exit 69; }

# 위치는 셈하지 않고 물어본다 — DCB_BACKUP_DIR 을 읽는 곳은 app.paths.백업자리 하나다
export DCB_DATA_DIR="$DATA"
BK="$(cd "$ROOT" && "$PY" scripts/backup.py --자리 2>&1)" || { say "$BK"; exit 78; }

if why="$(dcb_volume_problem "$BK")"; then :; else say "$why"; exit 69; fi

cd "$ROOT" || { say "저장소 폴더로 못 갑니다"; exit 69; }
msg="$(DCB_BACKUP_DIR="$BK" DCB_DATA_DIR="$DATA" "$PY" scripts/backup.py --신선도 "$AGE" 2>&1)"
rc=$?
case "$rc" in
  0) say "괜찮음 — $msg" ;;
  1) say "!! $msg" ;;
  *) say "!! 점검하지 못했습니다(backup.py 가 $rc) — $msg" ;;
esac
exit "$rc"
