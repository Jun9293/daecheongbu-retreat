#!/bin/bash
# 도는 동안 로그를 민다 — 사용자 권한 · sudo 없음 (docs/맥-이전.md).
# launchd(com.daecheongbu.logrotate)가 한 시간마다 부른다. 사람이 불러도 된다.
#
#   scripts/mac/로그밀기.sh                  기본 대상: <데이터>/server.log · <데이터>/launchd-*.log
#   scripts/mac/로그밀기.sh <파일> [<파일>…]  그 파일들만
#
# **옮기지 않고 복사한 뒤 비운다(copytruncate).** 서버와 cloudflared 는 파일을
# 연 채로 이어 쓰므로, 옮기면 옮긴 파일에 계속 쓴다. 둘 다 이어쓰기(O_APPEND)로
# 열어서 비운 뒤의 쓰기는 파일 앞에서 다시 시작한다.
# **대가** — 복사와 비우기 사이에 쓰인 몇 줄은 잃을 수 있다.
#
# 설정(.env · DCB_ENV_FILE)은 serve.sh 와 같은 env.sh 로 읽는다.
#   DCB_LOG_MAX_BYTES   기본 5242880 (5MB) — 넘은 것만 민다
#   DCB_LOG_KEEP        기본 1 (1~9) — .1 … .N 을 남긴다
#
# 밀 것이 없으면 아무 말도 안 한다 — 한 시간마다 「없음」 이 쌓이면 진짜 말이 묻힌다.
# 심볼릭 링크와 일반 파일이 아닌 것은 건드리지 않는다.

set -u
export PATH="/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/../.." && pwd -P)"

say() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] 로그밀기: $*" >&2; }

# shellcheck source=env.sh
. "$HERE/env.sh"
ENV_FILE="${DCB_ENV_FILE:-$ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
  dcb_load_env "$ENV_FILE"
elif [ -n "${DCB_ENV_FILE:-}" ]; then
  say "DCB_ENV_FILE 이 가리키는 파일이 없습니다: $ENV_FILE"; exit 78
fi

MAX="${DCB_LOG_MAX_BYTES:-5242880}"
KEEP="${DCB_LOG_KEEP:-1}"
if ! [[ "$MAX" =~ ^[0-9]+$ ]]; then say "DCB_LOG_MAX_BYTES 가 숫자가 아닙니다"; exit 78; fi
if ! [[ "$KEEP" =~ ^[1-9]$ ]]; then say "DCB_LOG_KEEP 은 1~9 입니다"; exit 78; fi

DATA="${DCB_DATA_DIR:-$ROOT/data}"
if [ "$#" -gt 0 ]; then
  files=("$@")
else
  files=("$DATA/server.log")
  for f in "$DATA"/launchd-*.log; do [ -e "$f" ] && files+=("$f"); done
fi

rc=0
for f in "${files[@]}"; do
  [ -e "$f" ] || continue
  if [ -L "$f" ] || [ ! -f "$f" ]; then say "일반 파일이 아니라 건너뜁니다: $f"; continue; fi
  size="$(stat -f '%z' "$f" 2>/dev/null || echo 0)"
  [ "$size" -gt "$MAX" ] || continue
  # 뒤에서부터 한 칸씩 민다: .N-1 → .N … .1 → .2
  i=$KEEP
  while [ "$i" -gt 1 ]; do
    [ -f "$f.$((i - 1))" ] && mv -f "$f.$((i - 1))" "$f.$i"
    i=$((i - 1))
  done
  if cp -p "$f" "$f.1" && : >"$f"; then
    say "밀었음: $(basename "$f") (${size}바이트 → .1)"
  else
    say "밀지 못했습니다: $f"; rc=1
  fi
done
exit "$rc"
