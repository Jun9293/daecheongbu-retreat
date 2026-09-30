#!/bin/bash
# plist 템플릿의 자리(__REPO__ · __HOME__ · __CLOUDFLARED__)를 채워 파일만 만든다.
# **로드하지 않는다** — launchctl 은 사람이(또는 전환하는 판이) 부른다.
#
#   scripts/mac/plist-만들기.sh <내보낼 폴더>
#   CLOUDFLARED=/경로/cloudflared scripts/mac/plist-만들기.sh <내보낼 폴더>
#
# 이미 같은 이름의 파일이 있으면 덮지 않고 멈춘다 — 돌고 있는 것의 정의를
# 말없이 바꾸지 않는다. 덮으려면 먼저 그 파일을 치운다.

set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/../.." && pwd -P)"
OUT="${1:?내보낼 폴더를 주세요}"
CF="${CLOUDFLARED:-/opt/homebrew/bin/cloudflared}"

# sed 치환에서 문제가 될 글자가 경로에 있으면 멈춘다
for v in "$ROOT" "$HOME" "$CF"; do
  case "$v" in *'|'*|*'&'*|*'\'*) echo "경로에 | & \\ 가 있어 만들 수 없습니다: $v" >&2; exit 1 ;; esac
done

mkdir -p "$OUT"
for t in "$HERE"/*.plist.template; do
  dst="$OUT/$(basename "$t" .template)"
  if [ -e "$dst" ]; then echo "이미 있습니다 — 안 덮습니다: $dst" >&2; exit 1; fi
  sed -e "s|__REPO__|$ROOT|g" -e "s|__HOME__|$HOME|g" -e "s|__CLOUDFLARED__|$CF|g" "$t" >"$dst"
  plutil -lint "$dst" >/dev/null
  echo "만듦: $dst"
done
[ -x "$CF" ] || echo "참고: $CF 가 아직 없습니다 — 터널 plist 는 설치 뒤에 씁니다" >&2
