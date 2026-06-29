#!/usr/bin/env python3
"""
Check specifically around position 72 in trial_guard.py
"""

import os

def check_position_72():
    print("=== CHECKING POSITION 72 IN TRIAL_GUARD.PY ===")
    print()
    
    # Get the path to trial_guard.py
    trial_guard_path = "E:/ho/arch/arch/trial_guard.py"
    
    # Read the file as bytes
    with open(trial_guard_path, 'rb') as f:
        content = f.read()
    
    # Check position 72 specifically
    if len(content) > 72:
        byte_at_72 = content[72]
        print(f"Position 72: byte value {byte_at_72}")
        
        # Check if it's a control character
        if byte_at_72 < 32:
            char_desc = {
                0: 'NUL',
                1: 'SOH',
                2: 'STX',
                3: 'ETX',
                4: 'EOT',
                5: 'ENQ',
                6: 'ACK',
                7: 'BEL',
                8: 'BS',
                9: 'HT (Tab)',
                10: 'LF (Line Feed)',
                11: 'VT (Vertical Tab)',
                12: 'FF (Form Feed)',
                13: 'CR (Carriage Return)',
                14: 'SO (Shift Out)',
                15: 'SI (Shift In)',
                16: 'DLE (Data Link Escape)',
                17: 'DC1 (Device Control 1)',
                18: 'DC2 (Device Control 2)',
                19: 'DC3 (Device Control 3)',
                20: 'DC4 (Device Control 4)',
                21: 'NAK (Negative Acknowledge)',
                22: 'SYN (Synchronous Idle)',
                23: 'ETB (End of Transmission Block)',
                24: 'CAN (Cancel)',
                25: 'EM (End of Medium)',
                26: 'SUB (Substitute)',
                27: 'ESC (Escape)',
                28: 'FS (File Separator)',
                29: 'GS (Group Separator)',
                30: 'RS (Record Separator)',
                31: 'US (Unit Separator)',
            }.get(byte_at_72, f'CTRL-{byte_at_72}')
            
            print(f"  This is a control character: {char_desc}")
            
            # Check if it's a newline
            if byte_at_72 == 10:
                print("  This is a Line Feed (LF), which is problematic in file paths")
            
            # Show context
            start = max(0, 72 - 10)
            end = min(len(content), 72 + 10)
            context = content[start:end]
            
            print(f"  Context (bytes {start}-{end}): {context}")
            
            # Try to decode context
            try:
                context_str = context.decode('utf-8')
                print(f"  Context (decoded): {repr(context_str)}")
            except UnicodeDecodeError:
                print(f"  Context (cannot decode): {context}")
        else:
            print(f"  This is not a control character")
            print(f"  Character: {chr(byte_at_72)}")
    else:
        print(f"File length is only {len(content)} bytes, so position 72 does not exist")
    
    # Also check the file name itself
    print()
    print("=== CHECKING FILE NAME ===")
    print(f"File name: {os.path.basename(trial_guard_path)}")
    print(f"File name bytes: {list(map(ord, os.path.basename(trial_guard_path)))}")

if __name__ == '__main__':
    check_position_72()
