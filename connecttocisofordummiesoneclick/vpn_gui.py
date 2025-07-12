#!/usr/bin/env python3
"""
Cisco AnyConnect VPN GUI Application
A simple Tkinter application to connect to various VPN servers using Cisco AnyConnect GUI.
"""

import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import subprocess
import threading
import time
import os
import json
import base64
from cryptography.fernet import Fernet
import getpass


class VPNConnector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Cisco AnyConnect VPN Connector")
        self.root.geometry("500x400")
        self.root.resizable(True, True)
        
        # Configuration file path
        self.config_file = os.path.join(os.path.expanduser("~"), ".vpn_config.json")
        
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
        
        # Load or setup credentials
        self.username, self.password = self.load_or_setup_credentials()
        
        self.setup_ui()
        
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
        
        # Settings button
        settings_btn = ttk.Button(
            control_frame,
            text="Reset Credentials",
            command=self.reset_credentials
        )
        settings_btn.grid(row=0, column=2, padx=5)
        
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
            self.update_status("Please complete the connection in the AnyConnect window:")
            self.update_status(f"  • Server: {server_url}")
            self.update_status(f"  • Username: {self.username}")
            self.update_status(f"  • Password: {self.password}")
            
            messagebox.showinfo(
                "AnyConnect Opened", 
                f"Cisco AnyConnect has been opened for {server_name}!\n\n"
                f"Server: {server_url}\n"
                f"Username: {self.username}\n"
                f"Password: {self.password}\n\n"
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


    def generate_key(self):
        """Generate a key for encryption based on machine info"""
        import platform
        machine_info = f"{platform.node()}{platform.machine()}{platform.processor()}"
        key = base64.urlsafe_b64encode(machine_info.encode()[:32].ljust(32, b'0'))
        return key
    
    def encrypt_data(self, data):
        """Encrypt sensitive data"""
        try:
            key = self.generate_key()
            f = Fernet(key)
            return f.encrypt(data.encode()).decode()
        except Exception:
            # Fallback to simple base64 encoding if encryption fails
            return base64.b64encode(data.encode()).decode()
    
    def decrypt_data(self, encrypted_data):
        """Decrypt sensitive data"""
        try:
            key = self.generate_key()
            f = Fernet(key)
            return f.decrypt(encrypted_data.encode()).decode()
        except Exception:
            # Fallback to base64 decoding
            try:
                return base64.b64decode(encrypted_data.encode()).decode()
            except Exception:
                return ""
    
    def save_credentials(self, username, password):
        """Save encrypted credentials to config file"""
        try:
            config = {
                "username": self.encrypt_data(username),
                "password": self.encrypt_data(password),
                "setup_complete": True
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save credentials: {str(e)}")
            return False
    
    def load_credentials(self):
        """Load and decrypt credentials from config file"""
        try:
            if not os.path.exists(self.config_file):
                return None, None
                
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            if not config.get("setup_complete", False):
                return None, None
                
            username = self.decrypt_data(config["username"])
            password = self.decrypt_data(config["password"])
            return username, password
        except Exception:
            return None, None
    
    def load_or_setup_credentials(self):
        """Load existing credentials or prompt user to set them up"""
        # Try to load existing credentials
        username, password = self.load_credentials()
        
        if username and password:
            return username, password
        
        # If no credentials found, show setup dialog
        return self.show_credentials_setup()
    
    def show_credentials_setup(self):
        """Show dialog for first-time credential setup"""
        setup_window = tk.Toplevel(self.root)
        setup_window.title("VPN Credentials Setup")
        setup_window.geometry("400x300")
        setup_window.resizable(False, False)
        setup_window.grab_set()  # Make it modal
        
        # Center the window
        setup_window.transient(self.root)
        setup_window.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 50,
            self.root.winfo_rooty() + 50
        ))
        
        # Variables to store credentials
        username_var = tk.StringVar()
        password_var = tk.StringVar()
        result = {"username": "", "password": ""}
        
        # Title
        title_label = ttk.Label(
            setup_window, 
            text="VPN Credentials Setup", 
            font=("Arial", 14, "bold")
        )
        title_label.pack(pady=20)
        
        # Instructions
        instruction_label = ttk.Label(
            setup_window,
            text="Please enter your VPN credentials.\nThese will be securely saved for future use.",
            justify=tk.CENTER
        )
        instruction_label.pack(pady=10)
        
        # Form frame
        form_frame = ttk.Frame(setup_window)
        form_frame.pack(pady=20, padx=40, fill=tk.X)
        
        # Username
        ttk.Label(form_frame, text="Username:").grid(row=0, column=0, sticky=tk.W, pady=5)
        username_entry = ttk.Entry(form_frame, textvariable=username_var, width=25)
        username_entry.grid(row=0, column=1, pady=5, padx=10)
        username_entry.focus()
        
        # Password
        ttk.Label(form_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=5)
        password_entry = ttk.Entry(form_frame, textvariable=password_var, show="*", width=25)
        password_entry.grid(row=1, column=1, pady=5, padx=10)
        
        # Buttons frame
        button_frame = ttk.Frame(setup_window)
        button_frame.pack(pady=20)
        
        def save_and_close():
            username = username_var.get().strip()
            password = password_var.get().strip()
            
            if not username or not password:
                messagebox.showerror("Error", "Please enter both username and password.")
                return
            
            if self.save_credentials(username, password):
                result["username"] = username
                result["password"] = password
                setup_window.destroy()
            
        def cancel_setup():
            setup_window.destroy()
            self.root.quit()  # Exit the application
        
        save_btn = ttk.Button(button_frame, text="Save & Continue", command=save_and_close)
        save_btn.pack(side=tk.LEFT, padx=10)
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel_setup)
        cancel_btn.pack(side=tk.LEFT, padx=10)
        
        # Handle Enter key
        def handle_enter(event):
            save_and_close()
        
        username_entry.bind('<Return>', handle_enter)
        password_entry.bind('<Return>', handle_enter)
        
        # Wait for window to close
        self.root.wait_window(setup_window)
        
        return result["username"], result["password"]
    
    def reset_credentials(self):
        """Reset saved credentials"""
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
            messagebox.showinfo("Reset Complete", "Credentials have been reset. Please restart the application.")
            self.root.quit()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to reset credentials: {str(e)}")


def main():
    """Main entry point"""
    app = VPNConnector()
    app.run()


if __name__ == "__main__":
    main()
