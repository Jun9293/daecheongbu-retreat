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
# - **로그는 스스로 민다** — 뜰 때 크기가 상한을 넘으면 .1 로 밀고 하나만 남긴다
#   (serve.bat 과 같은 규칙). 도는 동안에는 안 민다 — docs/맥-이전.md 5장.
# - **설정 파일의 값은 어디에도 찍지 않는다.** 틀린 줄은 줄 번호만 말한다.
# - 이미 환경에 있는 값이 설정 파일보다 이긴다(명시한 쪽이 이긴다).
#
# 설정 파일에서 이 스크립트만 쓰는 이름
#   DCB_PORT             기본 8000
#   DCB_LOG_FILE         기본 <데이터 폴더>/server.log · "-" 면 화면으로
#   DCB_LOG_MAX_BYTES    기본 5242880 (5MB)
# 나머지 DCB_* 는 앱이 읽는다 (docs/맥-이전.md 2장 · .env.example).

set -u

# bash 3.2(맥 기본)는 한글 변수·함수 이름을 못 받는다 — 이름은 ASCII 로 둔다
# launchd 는 PATH 를 거의 비워 준다 — lsof(/usr/sbin) 와 stat 을 찾게 한다
export PATH="/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/../.." && pwd -P)"
LOG=""

say() {
  # 뜨기 전의 말은 화면(= launchd 로그)과 서버 로그 둘 다에 남긴다 —
  # 한쪽만 남기면 사람이 여는 쪽에 없을 수 있다
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] serve.sh: $*"
  echo "$msg" >&2
  if [ -n "$LOG" ] && [ "$LOG" != "-" ]; then echo "$msg" >>"$LOG" 2>/dev/null || true; fi
}

# ── 설정 파일 ─────────────────────────────────────────────────────────
ENV_FILE="${DCB_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  # 권한이 넓으면 말만 한다 — 비밀값이 들 수 있는 파일이다
  perm="$(stat -f '%Lp' "$ENV_FILE" 2>/dev/null || echo '')"
  case "$perm" in
    ''|600|400) ;;
    *) say "경고: 설정 파일 권한이 $perm 입니다 — chmod 600 을 권합니다" ;;
  esac
  n=0
  # source 로 읽지 않는다 — 설정 파일이 명령을 실행하게 두지 않는다
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    line="${line#export }"
    key="${line%%=*}"
    if [ "$key" = "$line" ]; then say "설정 파일 ${n}번째 줄: '이름=값' 꼴이 아니라 건너뜁니다"; continue; fi
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    val="${line#*=}"
    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      say "설정 파일 ${n}번째 줄: 이름이 올바르지 않아 건너뜁니다"; continue
    fi
    # 양끝 따옴표 한 쌍만 벗긴다
    if [[ "$val" =~ ^\"(.*)\"$ ]] || [[ "$val" =~ ^\'(.*)\'$ ]]; then val="${BASH_REMATCH[1]}"; fi
    if [ -z "${!key+x}" ]; then export "$key=$val"; fi
  done <"$ENV_FILE"
elif [ -n "${DCB_ENV_FILE:-}" ]; then
  # 일부러 가리킨 파일이 없으면 기본값으로 돌지 않는다 — 조용히 다른 데이터로 뜬다
  say "DCB_ENV_FILE 이 가리키는 파일이 없습니다: $ENV_FILE"
  exit 78  # EX_CONFIG
fi

# ── 값 ────────────────────────────────────────────────────────────────
PORT="${DCB_PORT:-8000}"
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
  say "DCB_PORT 가 1024~65535 의 숫자가 아닙니다"
  exit 78
fi

DATA="${DCB_DATA_DIR:-$ROOT/data}"
if ! mkdir -p "$DATA" 2>/dev/null; then
  say "데이터 폴더를 만들 수 없습니다: $DATA"
  exit 73  # EX_CANTCREAT
fi

LOG="${DCB_LOG_FILE:-$DATA/server.log}"
MAXBYTES="${DCB_LOG_MAX_BYTES:-5242880}"
if ! [[ "$MAXBYTES" =~ ^[0-9]+$ ]]; then say "DCB_LOG_MAX_BYTES 가 숫자가 아닙니다"; exit 78; fi

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  say "가상환경이 없습니다: $ROOT/.venv — python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 69  # EX_UNAVAILABLE
fi

# ── 포트를 누가 쥐고 있나 ───────────────────────────────────────────
held="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | sort -u | tr '\n' ' ')"
if [ -n "${held// /}" ]; then
  who=""
  for p in $held; do who="$who $p($(ps -o comm= -p "$p" 2>/dev/null | xargs basename 2>/dev/null))"; done
  say "포트 $PORT 를 이미 쥐고 있습니다:$who — 건드리지 않고 끝냅니다"
  exit 75  # EX_TEMPFAIL — launchd 는 ThrottleInterval 뒤에 다시 부른다
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

cd "$ROOT" || { say "저장소 폴더로 못 갑니다: $ROOT"; exit 69; }
say "시작 pid=$$ port=$PORT (127.0.0.1)"

if [ "$LOG" != "-" ]; then exec >>"$LOG" 2>&1; fi
# exec 로 바꿔 탄다 — launchd 가 쥔 PID 가 곧 서버라 죽으면 바로 안다
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
