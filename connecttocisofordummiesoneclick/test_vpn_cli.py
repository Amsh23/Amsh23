#!/usr/bin/env python3
"""
Test script to verify Cisco AnyConnect CLI availability
"""

import subprocess
import sys
import os


def test_vpn_cli():
    """Test if the VPN CLI is available"""
    print("Testing Cisco AnyConnect CLI availability...")
    print("-" * 50)
    
    try:
        # Try to run vpn --help
        result = subprocess.run(
            ["vpn", "--help"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if result.returncode == 0:
            print("✅ SUCCESS: Cisco AnyConnect CLI is available!")
            print(f"Return code: {result.returncode}")
            print("\nCLI Output (first 10 lines):")
            lines = result.stdout.split('\n')[:10]
            for line in lines:
                if line.strip():
                    print(f"  {line}")
        else:
            print("❌ WARNING: VPN CLI returned non-zero exit code")
            print(f"Return code: {result.returncode}")
            print(f"Error output: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ ERROR: 'vpn' command not found!")
        print("\nTroubleshooting:")
        print("1. Ensure Cisco AnyConnect is installed")
        print("2. Add the AnyConnect installation directory to your PATH")
        print("3. On Windows, try adding: C:\\Program Files (x86)\\Cisco\\Cisco AnyConnect Secure Mobility Client\\")
        return False
        
    except subprocess.TimeoutExpired:
        print("❌ ERROR: VPN CLI test timed out")
        return False
        
    except Exception as e:
        print(f"❌ ERROR: Unexpected error - {e}")
        return False
    
    print("\n" + "-" * 50)
    print("Test completed. You can now run the VPN GUI application.")
    return True


if __name__ == "__main__":
    success = test_vpn_cli()
    if not success:
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)
