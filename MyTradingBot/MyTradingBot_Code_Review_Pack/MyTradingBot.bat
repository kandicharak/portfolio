@echo off
REM MyTradingBot Launcher - Desktop Shortcut Batch File
REM Double-click to start the application

cd /d "%~dp0"

echo Starting MyTradingBot...
echo Please wait while the application loads...

.venv\Scripts\python.exe MyTradingBot_Launcher.py

pause
