@echo off
REM 작업 스케줄러의 "시작 시" 트리거가 부르는 파일.
REM 창을 띄우지 않고 조용히 돈다 — run.bat 은 사람이 직접 켤 때 쓴다.
chcp 65001 > nul
cd /d "%~dp0.."

REM 127.0.0.1 에만 연다. 바깥은 Cloudflare 터널로만 들어온다.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> data\server.log 2>&1
