# MyTradingBot PowerShell Launcher
# Run: powershell -ExecutionPolicy Bypass -File run_mytradingbot.ps1

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

Write-Host "MyTradingBot Launcher" -ForegroundColor Green
Write-Host "=====================" -ForegroundColor Green

# Check prerequisites
if (-not (Test-Path ".venv")) {
    Write-Host "ERROR: Python virtual environment (.venv) not found!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path "streamlit_dhan_live_option_chain.py")) {
    Write-Host "ERROR: Application file (streamlit_dhan_live_option_chain.py) not found!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path "MyTradingBot_Launcher.py")) {
    Write-Host "ERROR: Launcher script (MyTradingBot_Launcher.py) not found!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "`nStarting application..." -ForegroundColor Yellow
Write-Host "The app window will open in your default browser."
Write-Host "Keep this window open while using the app.`n" -ForegroundColor Cyan

# Run the launcher
& .\.venv\Scripts\python.exe MyTradingBot_Launcher.py

Write-Host "`nApplication closed." -ForegroundColor Yellow
