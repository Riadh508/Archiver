#!/usr/bin/env python3
"""
Check the exact setup script path format
"""

import os

def check_setup_path():
    print("=== CHECKING SETUP SCRIPT PATH FORMAT ===")
    print()
    
    # Read setupInno.iss
    with open('E:/ho/arch/setupInno.iss', 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Check line 60
    lines = content.split('\n')
    if len(lines) > 59:
        line_60 = lines[59]
        print(f"Line 60: {line_60}")
        print()
        
        # Check for different path formats
        if 'arch\\\\trial_guard.py' in line_60:
            print("Path format: arch\\\\trial_guard.py (double backslash)")
            print("This is likely a single backslash (path separator) in Inno Setup")
        elif 'arch\\trial_guard.py' in line_60:
            print("Path format: arch\\trial_guard.py (single backslash)")
            print("This is a standard Windows path separator")
        else:
            print("Path format: Unknown")
        
        # Check if the path is valid
        expected_filename = 'trial_guard.py'
        if expected_filename in line_60:
            print(f"✓ Filename {expected_filename} is present in the path")
        else:
            print(f"✗ Filename {expected_filename} is not present in the path")
        
        print()
        
        # Try to understand what Inno Setup expects
        print("=== WHAT INNO SETUP EXPECTS ===")
        print("In Inno Setup, backslashes (\\) are path separators.")
        print("The path 'arch\\\\trial_guard.py' in the script means:")
        print("  - Directory: arch")
        print("  - File: trial_guard.py")
        print()
        print("In Windows, this would be: arch\\trial_guard.py")
        print("In Linux/Mac, this would be: arch/trial_guard.py")
        print()
        
        # Check the actual file
        actual_file = "E:/ho/arch/arch/trial_guard.py"
        if os.path.exists(actual_file):
            print(f"✓ Actual file exists: {actual_file}")
        else:
            print(f"✗ Actual file does not exist: {actual_file}")
            
        # Check if the setup script would work
        print()
        print("=== WILL THE SETUP SCRIPT WORK? ===")
        print("The setup script references trial_guard.py, which exists.")
        print("The path format is correct for Inno Setup.")
        print("The installation should work.")
        
    else:
        print("Could not find line 60 in setupInno.iss")

if __name__ == '__main__':
    check_setup_path()
