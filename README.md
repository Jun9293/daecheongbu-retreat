# 대청부 수련회 총무팀 통합 관리 시스템

대학청년부 수련회를 **준비 · 진행 · 정산**하는 모바일 우선 웹앱입니다.

담당 전도사와 총무팀장이 매 회차 바뀝니다. 잘 챙기는 사람이 맡으면 굴러가고
아니면 구멍이 생기는 구조를 없애는 것이 목적이고, 모든 설계 판단이 한 질문에
매여 있습니다 — **"누가 놓쳐도 시스템이 대신 알아차리는가?"**

---

## 무엇을 먼저 읽어야 하나

이 README 는 **무엇인지 · 어떻게 켜는지 · 어디를 읽어야 하는지**만 적습니다.
설계와 결정은 아래 문서가 유일한 기준입니다. **두 곳에 같은 것을 적으면
반드시 어긋나고, 어긋난 쪽을 아무도 눈치채지 못합니다.**

| 무엇을 알고 싶을 때 | 어디 |
|---|---|
| 왜 그렇게 만들었나 · 확정된 결정 · 데이터 모델 | **[CLAUDE.md](CLAUDE.md)** — 유일한 기준 문서 |
| 지금 어디까지 됐나 | [docs/review/최근.md](docs/review/최근.md) |
| 글로 적기 어려운 배치·간격·상태 표현 | [docs/mockups/](docs/mockups) 의 HTML |
| 집 서버에 올리는 절차 | [docs/배포-안내.md](docs/배포-안내.md) |
| 환경변수가 무엇무엇 있나 | [app/config.py](app/config.py) — 값마다 이유가 주석에 있습니다 |
| 어느 파일을 고쳐야 하나 | CLAUDE.md 14장의 표 |

---

## 실행

### 가장 쉬운 방법 (Windows)

`run.bat` 을 더블클릭하세요. 처음 실행하면 필요한 것을 알아서 설치합니다.
검은 창에 아래 주소가 보이면 성공입니다.

    http://127.0.0.1:8000

### 직접 명령어로

```bash
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe seed.py     # 업무 라이브러리와 첫 회차 (처음 한 번)
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

개발할 때는 `scripts\devserve.bat` 을 쓰세요 — **운영 데이터를 건드리지 않는
별도 폴더**에서 8001 포트로 뜹니다. 8001 이 이미 쓰이고 있으면(다른 창에서
띄워 둔 경우) `--port` 만 바꿔 직접 부르면 됩니다 — 데이터 폴더는 그대로입니다:

```bash
set DCB_DATA_DIR=%TEMP%\dcb-dev
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

> **서버를 켜 둔 채 코드를 고치지 마세요.** 파이썬은 켤 때 읽은 코드를 들고
> 있어서, 고친 것을 반영하려면 껐다 켜야 합니다. 화면이 이상하면 이것부터
> 확인하세요 (CLAUDE.md 11-2).

### 처음 로그인하기

로그인은 **초대 링크**로 합니다. 총무팀이 링크를 발급해 카카오톡으로 전달하고,
받은 사람이 그것을 한 번 열면 그 기기에 90일 동안 로그인됩니다.
(전화번호 SMS 인증은 접었습니다 — 이유는 CLAUDE.md 4-12.)

맨 처음 한 사람은 화면이 없으므로 명령어로 만듭니다.

```bash
.venv\Scripts\python.exe scripts\create_admin.py "이름" 01012341234
```

찍히는 주소를 그대로 열면 됩니다. 그다음부터는 `/admin/users` 화면에서 발급합니다.
**링크를 잃어버렸으면 계정을 다시 만들지 말고** 링크만 다시 받으세요 —
계정이 중복되면 알림이 그 수만큼 갑니다.

```bash
.venv\Scripts\python.exe scripts\create_admin.py --reissue 01012341234
```

### 휴대폰에서

PC 와 휴대폰이 같은 와이파이에 있으면 PC 의 IP 로 접속됩니다(`ipconfig` 로 확인).
브라우저 메뉴의 **홈 화면에 추가**를 누르면 앱처럼 씁니다(PWA).

> 웹 푸시는 브라우저 규격상 **HTTPS 또는 localhost 에서만** 켜집니다.
> `http://192.168.x.x` 로는 구독이 안 되고, 배포한 뒤 터널 주소로 들어오면 됩니다.

---

## 화면

사이드바 차례대로입니다.

| 경로 | 무엇 |
|---|---|
| `/board` | **준비 단계 보드** — D-주차 타임라인. 부서 → Main → 하위 트리, 상태·논의·첨부·진단 패널 |
| `/calendar` | **달력** — 마감일에 점 하나. "이번 주에 내가 뭘 해야 하나" |
| `/live` | **수련회 진행** — 현장용. 프로그램별 전/중/후 체크리스트 |
| `/live/staff` | **봉사팀 보기** — 봉사자 시간표. 화면과 엑셀이 같은 표 |
| `/setup` | **새 회차 만들기** — 4단계 마법사 |
| `/library` | **업무 라이브러리** — 회차를 넘어 남는 업무. 필수 지정·선후행 |
| `/draft` | **회차 준비** — 각 팀이 자기 칸을 채우고 제출 |
| `/admin/users` | **계정 관리** — 초대 링크 발급·재발급 |
| `/admin/notify/preview` | **알림 미리보기** — 오늘 누구에게 무엇이 갈지 (발송은 아직 안 켰습니다) |

`/meetings` `/budget` 등 **이전 설계에서 만든 화면이 아직 살아 있습니다.**
동작은 하지만 CLAUDE.md 의 스펙과 다른 화면이며, 각 Phase 에서 다시 만듭니다.
사이드바에 `재설계 예정` 으로 표시해 두었습니다.

---

## 들어 있는 데이터

`seed.py` 가 **2026 여름수련회 Belong** 한 회차와 업무 라이브러리를 넣습니다.
분류를 그럴듯하게 보이려고 **과거 회차를 지어내지 않습니다** — 지어낸 이력이
"필수 23건" 같은 판단의 근거가 되면 시스템 전체의 신뢰가 무너집니다.
그래서 마법사의 자동 분류는 쌓인 회차 수에 맞춰 표현을 바꿉니다 (CLAUDE.md 6-2).

부서는 CLAUDE.md 2장의 **9개**입니다. 행정·현장관리·비품·음식·교역자는 부서가
아니라 총무팀 안의 **파트**입니다.

> **저장소의 이름은 전부 가명입니다.** 진짜 이름과 기록은 `data/` 안에만 있고
> 올라가지 않습니다. 실명이 든 파일을 새로 만들어 커밋할 때만
> `scripts/anonymize.py` 를 돌리면 됩니다 (CLAUDE.md 11-2).

---

## 고쳤을 때 확인하는 법

```bash
.venv\Scripts\python.exe -m pytest              # 전부
.venv\Scripts\python.exe scripts\healthcheck.py # 자가진단 (DB·푸시·키·디스크·접속)
```

화면(상세 패널)을 고쳤으면 `docs/checks/drawer.js` 를 **보드와 달력 각각의**
콘솔에 붙여넣으세요. 패널은 두 화면이 같은 한 벌을 쓰므로 **한쪽만 통과하면
실제로는 한 벌이 아니라는 뜻입니다.** 규칙은 CLAUDE.md 10장에 있습니다.

---

## 기술 구성

Python 3.14 + FastAPI + SQLAlchemy 2.x + SQLite, Jinja2 서버 렌더링 + 순수 CSS
(빌드 도구·Node.js 없음), PWA + 웹 푸시(pywebpush + VAPID).
배포는 집 윈도우 서버 + Cloudflare Tunnel입니다.

```
app/
  main.py            앱 진입점, 라우터 연결, 오류 화면
  config.py          환경변수와 상한 — 값마다 이유가 주석에 있습니다
  models.py          데이터 모델 (CLAUDE.md 8장)
  security.py        세션 쿠키, 권한 가드
  domain/            순수 로직 (테스트가 주로 겨누는 곳)
  routers/           HTTP 라우트
  templates/         Jinja2 화면 · partials/drawer.html 은 보드·달력 공용
  static/            CSS · JS — drawer.js 도 보드·달력 공용
scripts/             첫 관리자·백업·자가진단·가져오기·가명화
docs/                CLAUDE.md 밖의 문서 · mockups · checks · review
tests/               도메인 테스트 + 실제 HTTP 통합 테스트
data/                SQLite DB, 업로드, 키 (전부 git 제외)
```

어느 기능이 어느 파일에 있는지는 **CLAUDE.md 14장의 표**가 최신입니다.

---

## 운영으로 넘어갈 때

절차는 [docs/배포-안내.md](docs/배포-안내.md) 에 있습니다 — 명령어를 아는 사람이
아니라 **처음 하는 사람 기준**으로 썼고, 각 단계에 "이렇게 나오면 성공"을 함께
적었습니다.

꼭 정해야 하는 환경변수는 둘입니다. 나머지는 [app/config.py](app/config.py) 를
보세요.

| 이름 | 왜 |
|---|---|
| `DCB_BASE_URL` | 바깥에서 보이는 주소. 초대 링크가 이 주소로 나갑니다 |
| `DCB_SECRET_KEY` | 세션 서명 키. 없으면 `data/secret_key.txt` 를 만들어 씁니다 — **그 파일은 백업 대상입니다** |

백업은 `scripts/backup.py` 가 매일 새벽에 돕니다. **`data/backups/` 를 폴더째
복사하지 마세요** — 업로드 zip 이 하드링크로 이어져 있어 USB·클라우드에서는
몇 배로 펼쳐집니다. 그 폴더 안의 `읽어보기.txt` 에 복사 명령이 있습니다.
