#!/bin/bash
# 맥에서 앱을 띄운다 — 윈도우의 scripts/serve.bat 자리 (docs/맥-이전.md).
#
# launchd(com.daecheongbu.app)가 부르고, 사람이 직접 불러도 된다.
#
#   scripts/mac/serve.sh            설정은 저장소 뿌리의 .env 에서 읽는다
#   DCB_ENV_FILE=경로 scripts/mac/serve.sh   다른 설정 파일로
#
# 지키는 것
# - **경로를 박지 않는다** — 저장소 뿌리와 venv 는 이 파일의 자리에서 센다.
# - **127.0.0.1 에만 연다.** 바깥은 터널로만 들어온다(공유기 포트를 안 연다).
#   그래서 주소는 설정으로 못 바꾸고 포트만 바꾼다.
# - **여러 번 불러도 안전하다** — 포트를 누가 쥐고 있으면 건드리지 않고
#   누구인지 말하고 75(EX_TEMPFAIL)로 끝난다. 남의 프로세스를 죽이지 않는다.
#   확인과 바인드 사이에 누가 먼저 잡아 uvicorn 이 바인드에 실패해도 같은 말 · 같은 75 다.
# - **설정 오류(78)는 같은 것을 한 번만 적는다** — launchd 는 30초마다 다시
#   부르므로 안 그러면 같은 줄이 하루 삼천 줄 쌓인다. 오류가 바뀌면 다시 적고,
#   한 번 제대로 뜨면 기록을 지운다. 기억은 $TMPDIR 에 두어 재부팅하면 다시 적는다.
# - **로그는 뜰 때 스스로 민다** — 크기가 상한을 넘으면 .1 로 밀고 하나만 남긴다
#   (serve.bat 과 같은 규칙). 도는 동안은 로그밀기.sh 가 민다.
# - **설정 파일의 값은 어디에도 찍지 않는다** — 읽는 규칙은 env.sh 하나다.
#
# 설정 파일에서 이 스크립트만 쓰는 이름
#   DCB_PORT             기본 8000
#   DCB_LOG_FILE         기본 <데이터 폴더>/server.log · "-" 면 화면으로
#   DCB_LOG_MAX_BYTES    기본 5242880 (5MB)
# 나머지 DCB_* 는 앱이 읽는다 (docs/맥-이전.md 2장 · .env.example).
#
# 시험 전용: DCB_SERVE_TEST_SKIP_PRECHECK=1 이면 포트 사전 확인을 건너뛴다
# (확인과 바인드 사이의 틈을 재현하려고 둔 것이다 — 운영 설정에 넣지 않는다).

set -u

# launchd 는 PATH 를 거의 비워 준다 — lsof(/usr/sbin) 와 stat 을 찾게 한다
export PATH="/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/../.." && pwd -P)"
LOG=""
BUF=""        # 뜨기 전의 말을 모아 둔다 — 설정 오류가 되풀이면 통째로 안 적으려고
FLUSHED=0
TO_LOG_ONLY=0 # 표준출력이 이미 로그로 돌려진 뒤인가

say() {
  if [ "$FLUSHED" = 1 ]; then _emit "$*"; else BUF="$BUF$*"$'\n'; fi
}

_emit() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] serve.sh: $1"
  echo "$msg" >&2
  # 뜨기 전의 말은 화면(= launchd 로그)과 서버 로그 둘 다에 남긴다 —
  # 한쪽만 남기면 사람이 여는 쪽에 없을 수 있다
  if [ "$TO_LOG_ONLY" = 0 ] && [ -n "$LOG" ] && [ "$LOG" != "-" ]; then
    echo "$msg" >>"$LOG" 2>/dev/null || true
  fi
}

flush() {
  FLUSHED=1
  local line
  while IFS= read -r line; do [ -n "$line" ] && _emit "$line"; done <<<"$BUF"
  BUF=""
}

# 같은 설정 오류는 한 번만 적는다 (위 머리말)
STATE="${TMPDIR:-/tmp}/daecheongbu-serve-$(printf '%s' "$ROOT|${DCB_ENV_FILE:-}" | cksum | cut -d' ' -f1).lasterr"
fail_config() {
  local now="$BUF$1"
  if [ -f "$STATE" ] && [ "$(cat "$STATE" 2>/dev/null)" = "$now" ]; then exit 78; fi
  printf '%s' "$now" >"$STATE" 2>/dev/null || true
  say "$1"
  flush
  say "같은 설정 오류는 고칠 때까지 다시 적지 않습니다 (종료 코드 78)"
  exit 78  # EX_CONFIG
}

port_holders() {
  local pids who="" p
  pids="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | sort -u | tr '\n' ' ')"
  for p in $pids; do who="$who $p($(ps -o comm= -p "$p" 2>/dev/null | xargs basename 2>/dev/null))"; done
  printf '%s' "$who"
}

busy_exit() {
  # 사전 확인에서든 바인드 실패에서든 **같은 말 · 같은 코드**로 끝낸다
  say "포트 $1 를 이미 쥐고 있습니다:$2 — 건드리지 않고 끝냅니다"
  flush
  exit 75  # EX_TEMPFAIL — launchd 는 ThrottleInterval 뒤에 다시 부른다
}

# ── 설정 파일 ─────────────────────────────────────────────────────────
# shellcheck source=env.sh
. "$HERE/env.sh"
ENV_FILE="${DCB_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  dcb_load_env "$ENV_FILE"
elif [ -n "${DCB_ENV_FILE:-}" ]; then
  # 일부러 가리킨 파일이 없으면 기본값으로 돌지 않는다 — 조용히 다른 데이터로 뜬다
  fail_config "DCB_ENV_FILE 이 가리키는 파일이 없습니다: $ENV_FILE"
fi

# ── 값 ────────────────────────────────────────────────────────────────
PORT="${DCB_PORT:-8000}"
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
  fail_config "DCB_PORT 가 1024~65535 의 숫자가 아닙니다"
fi

DATA="${DCB_DATA_DIR:-$ROOT/data}"
if ! mkdir -p "$DATA" 2>/dev/null; then
  fail_config "데이터 폴더를 만들 수 없습니다: $DATA"
fi

LOG="${DCB_LOG_FILE:-$DATA/server.log}"
MAXBYTES="${DCB_LOG_MAX_BYTES:-5242880}"
if ! [[ "$MAXBYTES" =~ ^[0-9]+$ ]]; then fail_config "DCB_LOG_MAX_BYTES 가 숫자가 아닙니다"; fi

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  fail_config "가상환경이 없습니다: $ROOT/.venv — python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
fi

# ── 포트를 누가 쥐고 있나 ───────────────────────────────────────────
if [ "${DCB_SERVE_TEST_SKIP_PRECHECK:-}" != 1 ]; then
  held="$(port_holders "$PORT")"
  if [ -n "${held// /}" ]; then busy_exit "$PORT" "$held"; fi
fi

# ── 로그 밀기 (뜰 때 한 번) ───────────────────────────────────────────
if [ "$LOG" != "-" ]; then
  mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
  if [ -f "$LOG" ]; then
    size="$(stat -f '%z' "$LOG" 2>/dev/null || echo 0)"
    if [ "$size" -gt "$MAXBYTES" ]; then mv -f "$LOG" "$LOG.1"; fi
  fi
  if ! touch "$LOG" 2>/dev/null; then
    LOG_BAD="$LOG"; LOG="-"
    say "로그 파일에 쓸 수 없습니다: $LOG_BAD — 화면으로 냅니다"
  fi
fi

cd "$ROOT" || fail_config "저장소 폴더로 못 갑니다: $ROOT"
rm -f "$STATE" 2>/dev/null
flush
say "시작 pid=$$ port=$PORT (127.0.0.1)"

if [ "$LOG" != "-" ]; then exec >>"$LOG" 2>&1; TO_LOG_ONLY=1; fi

# **exec 로 바꿔 타지 않는다** — uvicorn 이 실패로 끝났을 때 그것이 바인드
# 실패였는지 봐야 해서다. 대신 받은 신호는 그대로 넘기고 끝날 때까지 기다린다.
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
child=$!
trap 'kill -TERM "$child" 2>/dev/null' TERM INT HUP
while :; do
  wait "$child"; rc=$?
  kill -0 "$child" 2>/dev/null || break   # 신호로 wait 가 먼저 풀린 것이면 다시 기다린다
done
trap - TERM INT HUP

# 바인드에 실패한 uvicorn 은 **3** 으로 끝난다(1 이 아니다 — 2026-09-30 에 재 봄).
# 판마다 바뀔 수 있어 숫자 하나에 걸지 않고, 신호로 죽은 것(128 이상)만 빼고 본다.
if [ "$rc" != 0 ] && [ "$rc" -lt 128 ]; then
  held="$(port_holders "$PORT")"
  if [ -n "${held// /}" ]; then busy_exit "$PORT" "$held"; fi
fi
exit "$rc"
