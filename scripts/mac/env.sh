# 맥 스크립트가 함께 쓰는 설정 읽기 — serve.sh 와 로그밀기.sh 가 source 한다.
# **읽는 규칙은 여기 하나다** — 두 벌이면 한쪽만 고쳐진다.
#
# dcb_load_env <파일>
#   - source 로 읽지 않는다 — 설정 파일이 명령을 실행하게 두지 않는다
#   - **값은 어디에도 찍지 않는다.** 말하는 것은 줄 번호와 이름뿐이다
#   - `이름=값` 만 받는다. 앞의 `export ` 는 떼고, 양끝 따옴표 한 쌍은 벗긴다
#   - 따옴표 없는 값의 **줄 끝 주석**(빈칸 뒤 `#`)은 떼고 줄 번호로 알린다.
#     빈칸 없이 붙은 `#` 은 값의 일부로 둔다(주소의 `#` 같은 것)
#   - **환경에 이미 있는 이름이 이긴다.** 그때 이름만 한 줄 알린다
#
# 말은 부르는 쪽의 `say` 함수로 낸다. 없으면 표준오류로.
# bash 3.2(맥 기본)는 한글 변수·함수 이름을 못 받는다 — 이름은 ASCII 로 둔다.

_dcb_say() {
  if declare -F say >/dev/null; then say "$@"; else echo "$*" >&2; fi
}

dcb_load_env() {
  local file="$1" n=0 line key val perm
  perm="$(stat -f '%Lp' "$file" 2>/dev/null || echo '')"
  case "$perm" in
    ''|600|400) ;;
    *) _dcb_say "경고: 설정 파일 권한이 $perm 입니다 — chmod 600 을 권합니다" ;;
  esac
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1))
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    # 앞 빈칸 뒤에 # 만 있는 줄도 주석이다
    if [[ "$line" =~ ^[[:space:]]*# ]]; then continue; fi
    line="${line#export }"
    key="${line%%=*}"
    if [ "$key" = "$line" ]; then _dcb_say "설정 파일 ${n}번째 줄: '이름=값' 꼴이 아니라 건너뜁니다"; continue; fi
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    val="${line#*=}"
    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      _dcb_say "설정 파일 ${n}번째 줄: 이름이 올바르지 않아 건너뜁니다"; continue
    fi
    if [[ "$val" =~ ^[[:space:]]*\"(.*)\"[[:space:]]*$ ]] || [[ "$val" =~ ^[[:space:]]*\'(.*)\'[[:space:]]*$ ]]; then
      val="${BASH_REMATCH[1]}"
    else
      if [[ "$val" =~ ^(.*[^[:space:]])?[[:space:]]+#.*$ ]] || [[ "$val" =~ ^[[:space:]]*#.*$ ]]; then
        val="${BASH_REMATCH[1]:-}"
        _dcb_say "설정 파일 ${n}번째 줄: 줄 끝 주석을 값에서 떼었습니다 — 주석은 따로 한 줄에 적어 주세요"
      fi
      # 양끝 빈칸을 뗀다
      val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
    fi
    if [ -n "${!key+x}" ]; then
      _dcb_say "설정 파일 ${n}번째 줄: $key 는 환경에 이미 있어 그 값을 씁니다(설정 파일 값은 안 씀)"
      continue
    fi
    export "$key=$val"
  done <"$file"
}
