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
        self.username = "amir1382AT"
        self.password = "amir1382AT"
        
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
        """Actual VPN connection logic running in separate thread"""
        try:
            # Check if vpn command is available
            if not self._check_vpn_cli():
                self.update_status("ERROR: Cisco AnyConnect CLI 'vpn' command not found!")
                messagebox.showerror(
                    "VPN CLI Not Found", 
                    "Cisco AnyConnect CLI 'vpn' command not found!\n\n"
                    "Please ensure Cisco AnyConnect is installed and the CLI is available in PATH."
                )
                return
            
            # Prepare the connection commands
            commands = [
                f"connect {server_url}",
                self.username,
                self.password,
                "y"  # Accept certificate if prompted
            ]
            
            # Start the VPN process
            self.update_status("Starting AnyConnect CLI...")
            
            process = subprocess.Popen(
                ["vpn", "-s"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Send commands to the process
            input_data = "\n".join(commands) + "\n"
            self.update_status("Sending connection credentials...")
            
            try:
                stdout, stderr = process.communicate(input=input_data, timeout=30)
                
                # Process the output
                if process.returncode == 0:
                    self.update_status(f"Successfully connected to {server_name}!")
                    self.update_status("VPN Output:")
                    for line in stdout.strip().split('\n'):
                        if line.strip():
                            self.update_status(f"  {line.strip()}")
                    
                    messagebox.showinfo(
                        "VPN Connected", 
                        f"Successfully connected to {server_name}!\n\nServer: {server_url}"
                    )
                else:
                    self.update_status(f"Failed to connect to {server_name}")
                    error_msg = stderr.strip() if stderr.strip() else stdout.strip()
                    self.update_status(f"Error: {error_msg}")
                    
                    messagebox.showerror(
                        "VPN Connection Failed", 
                        f"Failed to connect to {server_name}.\n\nError: {error_msg}"
                    )
                    
            except subprocess.TimeoutExpired:
                process.kill()
                self.update_status("Connection attempt timed out")
                messagebox.showerror(
                    "Connection Timeout", 
                    "VPN connection attempt timed out after 30 seconds."
                )
                
        except FileNotFoundError:
            self.update_status("ERROR: 'vpn' command not found")
            messagebox.showerror(
                "VPN CLI Not Found", 
                "The 'vpn' command was not found.\n\n"
                "Please ensure Cisco AnyConnect is installed and the CLI is available."
            )
        except Exception as e:
            self.update_status(f"Unexpected error: {str(e)}")
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")
    
    def disconnect_vpn(self):
        """Disconnect from VPN"""
        self.update_status("Disconnecting from VPN...")
        
        thread = threading.Thread(target=self._disconnect_vpn_thread, daemon=True)
        thread.start()
    
    def _disconnect_vpn_thread(self):
        """Disconnect VPN in separate thread"""
        try:
            if not self._check_vpn_cli():
                self.update_status("ERROR: Cisco AnyConnect CLI 'vpn' command not found!")
                return
            
            process = subprocess.Popen(
                ["vpn", "disconnect"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            stdout, stderr = process.communicate(timeout=15)
            
            if process.returncode == 0:
                self.update_status("Successfully disconnected from VPN")
                messagebox.showinfo("VPN Disconnected", "Successfully disconnected from VPN.")
            else:
                error_msg = stderr.strip() if stderr.strip() else stdout.strip()
                self.update_status(f"Disconnect error: {error_msg}")
                messagebox.showwarning("Disconnect Warning", f"Disconnect completed with warning:\n{error_msg}")
                
        except subprocess.TimeoutExpired:
            process.kill()
            self.update_status("Disconnect operation timed out")
            messagebox.showerror("Timeout", "VPN disconnect operation timed out.")
        except Exception as e:
            self.update_status(f"Disconnect error: {str(e)}")
            messagebox.showerror("Error", f"Error during disconnect:\n{str(e)}")
    
    def _check_vpn_cli(self):
        """Check if VPN CLI is available"""
        try:
            subprocess.run(
                ["vpn", "--help"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def run(self):
        """Start the GUI application"""
        self.root.mainloop()


def main():
    """Main entry point"""
    app = VPNConnector()
    app.run()


if __name__ == "__main__":
    main()
