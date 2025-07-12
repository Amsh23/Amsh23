# Cisco AnyConnect VPN GUI

A simple Python GUI application for connecting to Cisco AnyConnect VPN servers using Tkinter.

## Features

- Simple and intuitive graphical interface
- Connect to 6 pre-configured VPN servers:
  - London: London.ipbama.com
  - Dubai: Dubai.ipbama.com
  - USA: Usa.ipbama.com
  - Netherlands: Netherlands.ipbama.com
  - Canada: Canada.ipbama.com
  - France: France.ipbama.com
- Real-time status updates
- Automatic credential handling
- VPN disconnect functionality
- Buildable as Windows executable

## Requirements

- Python 3.6+
- Cisco AnyConnect installed with CLI access
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

The VPN servers and credentials are configured in the `VPNConnector` class:

```python
# VPN Servers
self.vpn_servers = {
    "London": "London.ipbama.com",
    "Dubai": "Dubai.ipbama.com", 
    # ... add more servers here
}

# Credentials
self.username = "amir1382AT"
self.password = "amir1382AT"
```

To modify servers or credentials, edit these values in the `vpn_gui.py` file.

## How it works

1. The application uses the Cisco AnyConnect CLI (`vpn -s`) to establish connections
2. Connection commands are sent via subprocess with proper credential handling
3. All operations run in separate threads to prevent GUI freezing
4. Status updates are displayed in real-time
5. Success/error messages are shown via popup dialogs

## Troubleshooting

**"VPN CLI Not Found" error:**
- Ensure Cisco AnyConnect is installed
- Verify the `vpn` command is available in your system PATH
- On Windows, the CLI is typically located at: `C:\Program Files (x86)\Cisco\Cisco AnyConnect Secure Mobility Client\vpn.exe`

**Connection timeouts:**
- Check your internet connection
- Verify the VPN server URLs are correct
- Ensure your credentials are valid

## License

This project is provided as-is for educational and personal use.
