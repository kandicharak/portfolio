@echo off
title Zomato Intelligence Dashboard
color 0A
echo.
echo  ============================================
echo    ZOMATO INTELLIGENCE DASHBOARD
echo    Starting up... Please wait
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found!
    echo  Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Install dependencies if venv doesn't exist
if not exist ".venv" (
    echo  [SETUP] Creating virtual environment...
    python -m venv .venv
    echo  [SETUP] Installing dependencies... (first time only, ~2 min)
    .venv\Scripts\pip install -r requirements.txt --quiet
    echo  [SETUP] Done!
)

echo  [OK] Starting server on http://localhost:8000
echo  [OK] Opening browser...
echo.
echo  Press Ctrl+C to stop the server
echo.

:: Start server in background and open browser
start "" "http://localhost:8000"
.venv\Scripts\python server.py

pause
