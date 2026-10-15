@echo off
setlocal
cd /d "%~dp0"
echo ========================================================
echo   Starting 3Dollar ERP Server
echo   Portal:   http://127.0.0.1:8000/
echo   API Docs: http://127.0.0.1:8000/docs
echo ========================================================
python -m uvicorn src.channel_ui.web.app:app --host 0.0.0.0 --port 8000 --reload %*
