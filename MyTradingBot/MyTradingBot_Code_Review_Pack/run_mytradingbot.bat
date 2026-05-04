@echo off
REM MyTradingBot Desktop Launcher with Icon Support
REM This batch file can be wrapped in a shortcut to appear as an exe

SETLOCAL ENABLEDELAYEDEXPANSION

REM Get the directory where this script is located
SET SCRIPT_DIR=%~dp0

REM Change to the script directory
cd /d "%SCRIPT_DIR%"

REM Check if .venv exists
IF NOT EXIST ".venv" (
    echo ERROR: Python virtual environment not found!
    echo Please ensure .venv directory exists in: %SCRIPT_DIR%
    pause
    exit /b 1
)

REM Check if the app file exists
IF NOT EXIST "streamlit_dhan_live_option_chain.py" (
    echo ERROR: Application file not found!
    echo Expected: %SCRIPT_DIR%streamlit_dhan_live_option_chain.py
    pause
    exit /b 1
)

REM Check if the launcher exists
IF NOT EXIST "MyTradingBot_Launcher.py" (
    echo ERROR: Launcher script not found!
    echo Expected: %SCRIPT_DIR%MyTradingBot_Launcher.py
    pause
    exit /b 1
)

REM Hide the command window using VBScript trick
echo. > %TEMP%\launcher_invisible.vbs
echo Set objShell = CreateObject("WScript.Shell") >> %TEMP%\launcher_invisible.vbs
echo objShell.Run ".venv\Scripts\python.exe MyTradingBot_Launcher.py", 0, false >> %TEMP%\launcher_invisible.vbs

REM Run the application invisibly
cscript.exe %TEMP%\launcher_invisible.vbs
del %TEMP%\launcher_invisible.vbs

REM If we reach here, the app closed, so exit cleanly
exit /b 0
