@echo off
REM 개발용. 운영 데이터(data)를 건드리지 않도록 별도 폴더를 쓴다.
cd /d "%~dp0.."
set DCB_DATA_DIR=%TEMP%\dcb-dev
set DCB_SECRET_KEY=dev-only-secret
set DCB_DEV=1
if not exist "%DCB_DATA_DIR%\app.db" .venv\Scripts\python.exe seed.py
REM --reload 로 코드도 화면도 고치면 알아서 다시 읽는다.
REM 없으면 파이썬은 켤 때 읽은 코드를 들고 있는데 화면만 디스크에서
REM 다시 읽어서, 새 화면에 옛 코드가 짝지어져 500 이 난다.
REM .py 는 uvicorn 이 원래 본다. *.py 를 적으면 cmd 가 펼쳐 버린다.
REM 이 파일은 cp949 로 저장한다. UTF-8 로 두면 주석이 깨져 파싱이 틀어진다.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --reload-include "*.html"
