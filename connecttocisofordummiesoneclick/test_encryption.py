#!/usr/bin/env python3
"""
Quick test for credential management
"""

import sys
import os
sys.path.append('.')

from vpn_gui import VPNConnector

def test_encryption():
    """Test the encryption/decryption functions"""
    vpn = VPNConnector()
    
    # Test encryption
    test_data = "test_password_123"
    encrypted = vpn.encrypt_data(test_data)
    decrypted = vpn.decrypt_data(encrypted)
    
    print(f"Original: {test_data}")
    print(f"Encrypted: {encrypted}")
    print(f"Decrypted: {decrypted}")
    print(f"Match: {test_data == decrypted}")

if __name__ == "__main__":
    test_encryption()
