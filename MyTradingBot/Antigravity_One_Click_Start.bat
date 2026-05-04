@echo off
REM Antigravity Tracker - One Click Start

cd /d "%~dp0"

echo =======================================================
echo          🚀 ANTIGRAVITY ONE CLICK START 🚀
echo =======================================================
echo Starting the Antigravity Backend Bot and Dashboard...

.venv\Scripts\python.exe antigravity_webview_launcher.py

echo.
echo Application closed.
pause
