#!/usr/bin/env python3
"""
Check for potential issues with trial_guard.py file
"""

import os
import sys

def check_trial_guard_file():
    print("=== CHECKING TRIAL_GUARD.PY FILE ===")
    print()
    
    # Get the path to trial_guard.py
    trial_guard_path = "E:/ho/arch/arch/trial_guard.py"
    
    # Check if the file exists
    if not os.path.exists(trial_guard_path):
        print(f"ERROR: File not found: {trial_guard_path}")
        return False
    
    print(f"File exists: {trial_guard_path}")
    print(f"File size: {os.path.getsize(trial_guard_path)} bytes")
    print()
    
    # Read the file as bytes
    with open(trial_guard_path, 'rb') as f:
        content = f.read()
    
    print(f"File content (first 200 bytes, hex):")
    print(content[:200].hex())
    print()
    
    # Decode as UTF-8
    try:
        decoded = content.decode('utf-8')
        print(f"File content (first 200 chars, decoded):")
        print(repr(decoded[:200]))
        print()
        
        # Check for any issues
        issues = []
        
        # Check for control characters
        for i, char in enumerate(decoded):
            if ord(char) < 32 and char not in ['\\n', '\\r', '\\t']:
                issues.append(f"Control character at position {i}: {ord(char)}")
                break
        
        # Check for any non-ASCII characters
        non_ascii = [c for c in decoded if ord(c) > 127]
        if non_ascii:
            print(f"Non-ASCII characters found: {len(non_ascii)}")
            print(f"Non-ASCII characters: {non_ascii}")
            print(f"Non-ASCII character codes: {[ord(c) for c in non_ascii]}")
            print()
            
            # Check if the non-ASCII characters are problematic
            problematic_chars = [c for c in non_ascii if ord(c) > 0xff]  # Extended ASCII
            if problematic_chars:
                issues.append(f"Problematic non-ASCII characters: {problematic_chars}")
        
        # Check the first line
        first_line = decoded.split('\n')[0]
        print(f"First line: {repr(first_line)}")
        
        # Check if the file starts with the expected content
        expected_start = 'python -c "from arch.web import serve; serve()"'
        if not decoded.startswith(expected_start):
            issues.append(f"File does not start with expected content. Expected: {repr(expected_start)}")
        
        if issues:
            print(f"ISSUES FOUND:")
            for issue in issues:
                print(f"  - {issue}")
            return False
        else:
            print("No issues found with trial_guard.py file")
            return True
            
    except UnicodeDecodeError as e:
        print(f"ERROR: Failed to decode trial_guard.py as UTF-8: {e}")
        return False

def check_setup_script_reference():
    print()
    print("=== CHECKING SETUP SCRIPT REFERENCE ===")
    print()
    
    # Read setupInno.iss
    with open('E:/ho/arch/setupInno.iss', 'rb') as f:
        content = f.read()
    
    # Decode as UTF-8
    decoded = content.decode('utf-8', errors='ignore')
    
    # Check line 60
    lines = decoded.split('\n')
    if len(lines) > 59:
        line_60 = lines[59]
        print(f"Line 60: {line_60}")
        
        # Check if it references trial_guard.py
        if 'trial_guard.py' in line_60:
            print("✓ Setup script correctly references trial_guard.py")
            
            # Check if the path is correct
            if 'arch\\\\trial_guard.py' in line_60 or 'arch\\trial_guard.py' in line_60:
                print("✓ Path format is correct (arch\\trial_guard.py)")
            else:
                print("✗ Path format may be incorrect")
                
            return True
        else:
            print("✗ Setup script does not reference trial_guard.py")
            return False
    else:
        print("✗ Could not find line 60 in setupInno.iss")
        return False

if __name__ == '__main__':
    print("Professional Archiving System - Installation Issue Fixer")
    print("=" * 60)
    print()
    
    file_ok = check_trial_guard_file()
    setup_ok = check_setup_script_reference()
    
    print()
    print("=== SUMMARY ===")
    print(f"trial_guard.py file: {'OK' if file_ok else 'ISSUES FOUND'}")
    print(f"Setup script reference: {'OK' if setup_ok else 'ISSUES FOUND'}")
    
    if file_ok and setup_ok:
        print()
        print("All checks passed. If there is still an installation error,")
        print("it might be unrelated to the files we've checked.")
        print("The error could be in the installation process itself,")
        print("or in how the files are being processed during installation.")
    else:
        print()
        print("Issues found. Please review the output above.")
        print()
        print("Recommended fix:")
        print("1. Ensure trial_guard.py is properly encoded as UTF-8")
        print("2. Verify the setupInno.iss file has the correct path format")
        print("3. Check if the file has any hidden characters or encoding issues")
