@echo off
REM 작업 스케줄러의 "시작 시" 트리거가 부르는 파일.
REM 창을 띄우지 않고 조용히 돈다 — run.bat 은 사람이 직접 켤 때 쓴다.
chcp 65001 > nul
cd /d "%~dp0.."

REM data 폴더가 없어도 죽지 않게 (첫 실행)
if not exist "data" mkdir "data"

REM 로그가 5MB 를 넘으면 한 번 밀고 새로 시작한다. 이전 것 하나만 남긴다 —
REM 덧붙이기만 하면 몇 달 뒤 몇 백 MB 가 되고, 하필 data\ 안이라
REM 그 폴더를 USB 에 복사할 때 함께 딸려온다.
set "LOG=data\server.log"
set "MAXBYTES=5242880"
if exist "%LOG%" (
  for %%F in ("%LOG%") do set "LOGSIZE=%%~zF"
  setlocal enabledelayedexpansion
  if !LOGSIZE! GTR %MAXBYTES% (
    if exist "%LOG%.1" del "%LOG%.1"
    move /y "%LOG%" "%LOG%.1" > nul
  )
  endlocal
)

REM 127.0.0.1 에만 연다. 바깥은 Cloudflare 터널로만 들어온다.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%LOG%" 2>&1
