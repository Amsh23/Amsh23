# Installation and Setup Guide

## Quick Setup

1. **Download and Install:**
   - Download the files or clone the repository
   - Install Python 3.6+ if not already installed

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **First Run:**
   - Run the application: `python vpn_gui.py`
   - On first launch, you'll be prompted to enter your VPN credentials
   - Enter your username and password once - they will be securely saved

4. **Usage:**
   - Click any server button to connect
   - Your credentials are automatically remembered
   - AnyConnect will open with the server pre-filled

## Building Executable

To create a standalone .exe file:

```bash
# Option 1: Use the batch file
build_exe.bat

# Option 2: Use PowerShell script
build_exe.ps1

# Option 3: Manual build
pyinstaller --onefile --windowed --name "VPN_Connector" vpn_gui.py
```

## Security Features

- ✅ **Credentials are encrypted** using machine-specific keys
- ✅ **No plaintext passwords** stored anywhere
- ✅ **Config file is hidden** and ignored by Git
- ✅ **One-time setup** - enter credentials only once
- ✅ **Reset option** available if needed

## Troubleshooting

**"Credential Setup" window appears every time:**
- Make sure you have write permissions to your home directory
- Check if `.vpn_config.json` file is being created in your home folder

**"Reset Credentials" not working:**
- The config file is located at: `%USERPROFILE%\.vpn_config.json`
- You can manually delete this file to reset credentials

**Application won't start:**
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check if Cisco AnyConnect is installed properly
