#! /usr/bin/env python3
"""
Check and fix setupInno.iss file
"""

import os
import re

def check_setup_script():
    print("=== Checking setupInno.iss ===")
    
    with open('E:/ho/arch/setupInno.iss', 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Check for any lines with Source that might have issues
    lines = content.split('\n')
    
    print(f"Total lines: {len(lines)}")
    
    # Look for any lines with Source that might have issues
    for i, line in enumerate(lines, 1):
        if 'Source:' in line:
            print(f"Line {i}: {line}")
            
            # Check if it has a tab character
            if '\\t' in line:
                print(f"  WARNING: Contains TAB character!")
                
            # Check for any other issues
            if 'trial_guard' in line.lower():
                print(f"  INFO: Contains trial_guard.py")
                
            # Check if the file exists
            # Extract the filename
            match = re.search(r'Source:\s*"([^"]+)"', line)
            if match:
                filepath = match.group(1)
                print(f"  Filepath: {filepath}")
                
                # Check if the file exists
                if os.path.exists(filepath):
                    print(f"  OK: File exists")
                else:
                    print(f"  WARNING: File does not exist")
    
    print("\n=== Checking for any potential issues ===")
    
    # Check for any lines with tab characters
    tab_lines = []
    for i, line in enumerate(lines, 1):
        if '\t' in line:
            tab_lines.append((i, line))
    
    if tab_lines:
        print(f"Found {len(tab_lines)} lines with tab characters:")
        for i, line in tab_lines:
            print(f"  Line {i}: {line}")
    else:
        print("No tab characters found in setupInno.iss")
    
    print("\n=== Check complete ===")

if __name__ == '__main__':
    check_setup_script()