# MyTradingBot Launcher Guide

## Quick Start

You have multiple ways to run MyTradingBot:

### Option 1: Batch File (Recommended for Windows)
**File:** `run_mytradingbot.bat`
- Double-click `run_mytradingbot.bat` to start the application
- A console window will appear showing the startup process
- Your browser will automatically open with the trading application
- Keep the console window open while using the app

### Option 2: Hidden Batch File
**File:** `MyTradingBot.bat`
- Similar to Option 1 but runs with a hidden console window
- Double-click to start

### Option 3: PowerShell Script
**File:** `run_mytradingbot.ps1`
- Right-click and select "Run with PowerShell"
- Or run: `powershell -ExecutionPolicy Bypass -File run_mytradingbot.ps1`

### Option 4: Direct Python
```bash
.\.venv\Scripts\python.exe MyTradingBot_Launcher.py
```

## Creating a Desktop Shortcut (Looks like .exe)

### For Windows:
1. Right-click on your Desktop → New → Shortcut
2. Enter this path:
   ```
   %SystemRoot%\System32\cmd.exe /C "D:\MyTradingBot\run_mytradingbot.bat"
   ```
   (Replace `D:\MyTradingBot` with your actual installation path)
3. Click Next
4. Name it: `MyTradingBot`
5. Click Finish
6. Right-click the shortcut → Properties
7. Click "Change Icon..."
8. Choose any icon from `%SystemRoot%\System32\shell32.dll` (or provide your own .ico file)
9. Click Apply → OK

Now you have a desktop shortcut that launches the app!

## Port Management

The launcher automatically finds an available port if the default port (8765) is busy. You don't need to worry about port conflicts.

### How it works:
- If port 8765 is available, it uses that
- If busy, it tries ports 8765-8814
- The app URL will be displayed in the console

## Troubleshooting

### Issue: "Python virtual environment not found"
- Solution: Make sure `.venv` folder exists in the MyTradingBot directory

### Issue: "Application file not found"
- Solution: Ensure `streamlit_dhan_live_option_chain.py` is in the MyTradingBot directory

### Issue: Blank/white page in browser
- Solution: The launcher automatically handles this with proper port management
- Wait 10-20 seconds for the app to fully load
- Refresh the page if needed (Ctrl+R)

### Issue: Port already in use
- Solution: Automatic - the launcher will find another available port

### Issue: Cannot run batch file
- Make sure file extension is `.bat` (not `.txt`)
- Try: Right-click → Run as Administrator

## System Requirements

- Python 3.9+
- Windows 10/11 (or Windows Server)
- 2GB RAM minimum
- Internet connection recommended (for data loading)

## Files Needed

For the launcher to work, you need:
- `MyTradingBot_Launcher.py` - Main launcher script
- `streamlit_dhan_live_option_chain.py` - Application
- `requirements.txt` - Python dependencies
- `.venv/` - Python virtual environment
- `Dhan_Nifty_Master.csv` - Instrument master data
- `Daily_Futures_Data/` - Historical data (optional)
- `Daily_Options_Data/` - Historical data (optional)

## Advanced: Creating a True .exe File

If you need a standalone `.exe` file:

```bash
.\.venv\Scripts\python.exe -m PyInstaller --onedir --windowed --name "MyTradingBot" --hidden-import=streamlit MyTradingBot_Launcher.py
```

This creates: `dist\MyTradingBot\MyTradingBot.exe`

## Support

If you encounter issues:
1. Check that all required files are present
2. Verify the `.venv` is properly set up
3. Try running from the command line directly
4. Check that no other app is using port 8765

Enjoy your trading application!
