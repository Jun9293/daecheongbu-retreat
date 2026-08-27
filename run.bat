@echo off
REM 대청부 수련회 관리 시스템 실행 (Windows)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/2] 가상환경을 만드는 중...
  py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install -q -r requirements.txt
)
echo.
echo   http://127.0.0.1:8000  으로 접속하세요. (같은 와이파이의 휴대폰에서도 접속 가능)
echo   종료하려면 Ctrl+C
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
