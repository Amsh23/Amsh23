@echo off
echo Starting Cisco AnyConnect VPN GUI...
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.6+ first.
    pause
    exit /b 1
)

REM Run the VPN GUI application
python vpn_gui.py

echo.
echo Application closed.
pause
