@echo off
chcp 65001 > nul
title 대청부 수련회 관리 시스템
cd /d "%~dp0"

echo.
echo   대청부 수련회 총무팀 관리 시스템
echo   ================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo   [준비] 처음 실행이라 필요한 것들을 설치합니다. 몇 분 걸릴 수 있어요...
  py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install -q -r requirements.txt
  echo   [준비] 설치 완료.
  echo.
)

if not exist "data\app.db" (
  echo   [준비] 처음이라 데모 데이터를 만듭니다...
  .venv\Scripts\python.exe seed.py
  echo.
)

echo   잠시 후 브라우저가 자동으로 열립니다.
echo.
echo   주소   : http://127.0.0.1:8000
echo   로그인 : 010-1111-2222   (인증번호는 화면에 표시됩니다)
echo.
echo   ** 이 검은 창을 닫으면 프로그램이 종료됩니다. **
echo.

start "" /b cmd /c "timeout /t 4 /nobreak > nul & start """" http://127.0.0.1:8000"

.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo   프로그램이 종료되었습니다. 아무 키나 누르면 창이 닫힙니다.
pause > nul
