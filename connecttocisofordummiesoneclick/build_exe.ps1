# PowerShell script to build the VPN GUI executable
Write-Host "Building Cisco AnyConnect VPN GUI executable..." -ForegroundColor Green

# Check if Python is available
try {
    $pythonVersion = python --version
    Write-Host "Python found: $pythonVersion" -ForegroundColor Yellow
} catch {
    Write-Host "ERROR: Python not found. Please install Python 3.6+ first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Install PyInstaller if not already installed
Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
pip install pyinstaller

# Build the executable
Write-Host "Building executable with PyInstaller..." -ForegroundColor Yellow
pyinstaller --onefile --windowed --name "VPN_Connector" vpn_gui.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild completed successfully!" -ForegroundColor Green
    Write-Host "Executable location: dist\VPN_Connector.exe" -ForegroundColor Cyan
    
    # Check if executable exists
    if (Test-Path "dist\VPN_Connector.exe") {
        Write-Host "✅ Executable file verified!" -ForegroundColor Green
        
        # Ask if user wants to run the test
        $runTest = Read-Host "`nDo you want to test the VPN CLI availability? (y/n)"
        if ($runTest -eq "y" -or $runTest -eq "Y") {
            Write-Host "`nRunning VPN CLI test..." -ForegroundColor Yellow
            python test_vpn_cli.py
        }
    } else {
        Write-Host "❌ Warning: Executable file not found at expected location" -ForegroundColor Red
    }
} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
}

Write-Host "`nPress Enter to exit..." -ForegroundColor Gray
Read-Host
