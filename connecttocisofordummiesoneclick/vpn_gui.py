#!/usr/bin/env python3
"""
Cisco AnyConnect VPN GUI Application
A simple Tkinter application to connect to various VPN servers using Cisco AnyConnect CLI.
"""

import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import threading
import time
import os


class VPNConnector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Cisco AnyConnect VPN Connector")
        self.root.geometry("500x400")
        self.root.resizable(True, True)
        
        # VPN Configuration
        self.config_path = os.path.join(os.path.dirname(__file__), "vpn_config.json")
        self.username = None
        self.password = None
        self.load_credentials()
        
        # VPN Paths
        self.vpn_gui_path = r"C:\Program Files (x86)\Cisco\Cisco AnyConnect Secure Mobility Client\vpnui.exe"
        self.vpn_cli_path = r"C:\Program Files (x86)\Cisco\Cisco AnyConnect Secure Mobility Client\vpncli.exe"
        
        # VPN Servers
        self.vpn_servers = {
            "London": "London.ipbama.com",
            "Dubai": "Dubai.ipbama.com", 
            "USA": "Usa.ipbama.com",
            "Netherlands": "Netherlands.ipbama.com",
            "Canada": "Canada.ipbama.com",
            "France": "France.ipbama.com"
        }
        
        self.setup_ui()
        if not self.username or not self.password:
            self.show_credentials_form()
    def load_credentials(self):
        """Load credentials from config file if exists"""
        import json
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.username = data.get("username")
                    self.password = data.get("password")
            except Exception:
                self.username = None
                self.password = None

    def save_credentials(self, username, password):
        """Save credentials to config file"""
        import json
        self.username = username
        self.password = password
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"username": username, "password": password}, f)

    def show_credentials_form(self):
        """Show a simple form to enter credentials"""
        cred_win = tk.Toplevel(self.root)
        cred_win.title("Set VPN Credentials")
        cred_win.geometry("300x180")
        cred_win.grab_set()

        tk.Label(cred_win, text="Enter your VPN username:").pack(pady=(20,5))
        username_entry = tk.Entry(cred_win)
        username_entry.pack(pady=5)

        tk.Label(cred_win, text="Enter your VPN password:").pack(pady=5)
        password_entry = tk.Entry(cred_win, show="*")
        password_entry.pack(pady=5)

        def save_and_close():
            user = username_entry.get().strip()
            pwd = password_entry.get().strip()
            if not user or not pwd:
                messagebox.showerror("Error", "Username and password cannot be empty!")
                return
            self.save_credentials(user, pwd)
            cred_win.destroy()
            self.update_status("Credentials saved successfully.")

        tk.Button(cred_win, text="Save", command=save_and_close).pack(pady=15)
        
    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights for responsive design
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="Cisco AnyConnect VPN Connector", 
            font=("Arial", 16, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 20))
        
        # Instructions
        instructions = ttk.Label(
            main_frame,
            text="Click a button below to connect to the corresponding VPN server:",
            font=("Arial", 10)
        )
        instructions.grid(row=1, column=0, pady=(0, 15))
        
        # Server buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=2, column=0, pady=(0, 20), sticky=(tk.W, tk.E))
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)
        
        # Create buttons for each VPN server
        row = 0
        col = 0
        for server_name, server_url in self.vpn_servers.items():
            btn = ttk.Button(
                buttons_frame,
                text=f"Connect to {server_name}",
                command=lambda name=server_name, url=server_url: self.connect_vpn(name, url),
                width=20
            )
            btn.grid(row=row, column=col, padx=5, pady=5, sticky=(tk.W, tk.E))
            
            col += 1
            if col > 1:  # 2 columns layout
                col = 0
                row += 1
        
        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=3, column=0, pady=(10, 0), sticky=(tk.W, tk.E, tk.N, tk.S))
        status_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Status text
        self.status_text = tk.Text(
            status_frame, 
            height=8, 
            width=50, 
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar for status text
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.status_text.configure(yscrollcommand=scrollbar.set)
        
        # Configure text widget grid
        status_frame.rowconfigure(0, weight=1)
        
        # Control buttons frame
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=4, column=0, pady=(10, 0))
        
        # Disconnect button
        disconnect_btn = ttk.Button(
            control_frame,
            text="Disconnect VPN",
            command=self.disconnect_vpn
        )
        disconnect_btn.grid(row=0, column=0, padx=5)
        
        # Clear status button
        clear_btn = ttk.Button(
            control_frame,
            text="Clear Status",
            command=self.clear_status
        )
        clear_btn.grid(row=0, column=1, padx=5)
        
        # Initial status message
        self.update_status("Ready to connect. Select a VPN server above.")
    
    def update_status(self, message):
        """Update the status text widget"""
        self.status_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update()
    
    def clear_status(self):
        """Clear the status text"""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.update_status("Status cleared.")
    
    def connect_vpn(self, server_name, server_url):
        """Connect to VPN server in a separate thread"""
        self.update_status(f"Connecting to {server_name} ({server_url})...")
        
        # Run connection in separate thread to prevent GUI freezing
        thread = threading.Thread(
            target=self._connect_vpn_thread, 
            args=(server_name, server_url),
            daemon=True
        )
        thread.start()
    
    def _connect_vpn_thread(self, server_name, server_url):
        """Connect to VPN by opening Cisco AnyConnect GUI with server URL"""
        try:
            # Check if Cisco AnyConnect GUI is available
            if not os.path.exists(self.vpn_gui_path):
                self.update_status("ERROR: Cisco AnyConnect GUI not found!")
                messagebox.showerror(
                    "VPN GUI Not Found", 
                    f"Cisco AnyConnect GUI not found at:\n{self.vpn_gui_path}\n\n"
                    "Please ensure Cisco AnyConnect is installed properly."
                )
                return
            
            self.update_status(f"Opening Cisco AnyConnect for {server_name}...")
            self.update_status(f"Server URL: {server_url}")
            
            # Open Cisco AnyConnect GUI with the server URL
            # This will open AnyConnect and pre-fill the server address
            subprocess.Popen(
                [self.vpn_gui_path, "-url", server_url],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            self.update_status("✅ Cisco AnyConnect opened successfully!")
            self.update_status("Please complete the connection in the AnyConnect window.")
            self.update_status(f"  • Server: {server_url}")
            messagebox.showinfo(
                "AnyConnect Opened", 
                f"Cisco AnyConnect has been opened for {server_name}!\n\n"
                f"Server: {server_url}\n\n"
                "Please complete the connection in the AnyConnect window."
            )
                
        except Exception as e:
            self.update_status(f"Error opening AnyConnect: {str(e)}")
            messagebox.showerror("Error", f"An error occurred while opening AnyConnect:\n{str(e)}")
    
    def disconnect_vpn(self):
        """Open AnyConnect to manually disconnect"""
        self.update_status("Opening AnyConnect for manual disconnect...")
        
        thread = threading.Thread(target=self._disconnect_vpn_thread, daemon=True)
        thread.start()
    
    def _disconnect_vpn_thread(self):
        """Open AnyConnect GUI for disconnect"""
        try:
            if not os.path.exists(self.vpn_gui_path):
                self.update_status("ERROR: Cisco AnyConnect GUI not found!")
                return
            
            # Simply open AnyConnect GUI - user can disconnect manually
            subprocess.Popen(
                [self.vpn_gui_path],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            self.update_status("✅ AnyConnect opened for disconnect")
            messagebox.showinfo("AnyConnect Opened", "AnyConnect has been opened.\nYou can disconnect manually from the AnyConnect window.")
        except Exception as e:
            self.update_status(f"Error opening AnyConnect: {str(e)}")
            messagebox.showerror("Error", f"An error occurred while opening AnyConnect:\n{str(e)}")
    
    def _check_vpn_cli(self):
        """Check if VPN GUI is available"""
        return os.path.exists(self.vpn_gui_path)
    
    def run(self):
        """Start the GUI application"""
        self.root.mainloop()


def main():
    """Main entry point"""
    app = VPNConnector()
    app.run()


if __name__ == "__main__":
    main()
