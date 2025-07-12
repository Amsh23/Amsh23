@echo off
echo Building Cisco AnyConnect VPN GUI executable...

REM Install PyInstaller if not already installed
pip install pyinstaller

REM Build the executable
pyinstaller --onefile --windowed --name "VPN_Connector" vpn_gui.py

echo.
echo Build complete! 
echo Executable can be found in: dist\VPN_Connector.exe
echo.
pause
