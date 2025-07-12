# Cisco AnyConnect VPN GUI - One-Click Connection

A simple Python GUI application that opens Cisco AnyConnect with pre-configured VPN servers for easy connection.

## Features

- Simple and intuitive graphical interface
- One-click access to 6 pre-configured VPN servers:
  - London: London.ipbama.com
  - Dubai: Dubai.ipbama.com
  - USA: Usa.ipbama.com
  - Netherlands: Netherlands.ipbama.com
  - Canada: Canada.ipbama.com
  - France: France.ipbama.com
- Opens Cisco AnyConnect GUI automatically with server pre-filled
- Secure credential storage (enter once, use forever)
- Perfect for non-technical users
- Buildable as Windows executable

## How it Works

1. Click a server button in the GUI
2. Cisco AnyConnect opens automatically with the server URL pre-filled
3. Enter your VPN credentials in AnyConnect (first time setup will prompt for these)
4. Click Connect in AnyConnect

## Requirements

- Python 3.6+
- Cisco AnyConnect installed (GUI version)
- Windows OS (for executable build)

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Running the Python script
```bash
python vpn_gui.py
```

### Building Windows executable
Run the provided batch file:
```bash
build_exe.bat
```

Or manually with PyInstaller:
```bash
pyinstaller --onefile --windowed --name "VPN_Connector" vpn_gui.py
```

The executable will be created in the `dist` folder.

## Configuration

The VPN servers are pre-configured. Your credentials will be securely saved after first use.

For first-time setup:
1. Run the application
2. Enter your VPN username and password when prompted
3. Credentials are saved locally and encrypted
4. Future connections will use saved credentials automatically

```python
# VPN Servers (pre-configured)
self.vpn_servers = {
    "London": "London.ipbama.com",
    "Dubai": "Dubai.ipbama.com", 
    # ... other servers
}
```

To modify servers, edit the `vpn_servers` dictionary in the `vpn_gui.py` file.

## How it works

1. The application opens Cisco AnyConnect GUI automatically when you click a server button
2. The server URL is pre-filled in AnyConnect
3. You just need to enter your VPN credentials (first time only)
4. Perfect for non-technical users who want easy VPN access
5. No command-line knowledge required

## Troubleshooting

**"VPN GUI Not Found" error:**
- Ensure Cisco AnyConnect is installed
- Verify the GUI is at: `C:\Program Files (x86)\Cisco\Cisco AnyConnect Secure Mobility Client\vpnui.exe`

**AnyConnect doesn't open:**
- Check if Cisco AnyConnect is properly installed
- Try running AnyConnect manually first to ensure it works

## License

This project is provided as-is for educational and personal use.
