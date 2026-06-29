#!/usr/bin/env python3
"""
Check for control character in trial_guard.py file
"""

import os

def find_control_characters():
    print("=== FINDING CONTROL CHARACTERS IN TRIAL_GUARD.PY ===")
    print()
    
    # Get the path to trial_guard.py
    trial_guard_path = "E:/ho/arch/arch/trial_guard.py"
    
    # Read the file as bytes
    with open(trial_guard_path, 'rb') as f:
        content = f.read()
    
    # Find control characters
    control_chars = []
    for i, byte in enumerate(content):
        if byte < 32 and byte not in [9, 10, 13]:  # Skip tab, LF, CRLF
            control_chars.append((i, byte))
    
    if control_chars:
        print(f"Found {len(control_chars)} control characters:")
        for i, byte in control_chars:
            char_repr = {
                0: 'NUL',
                1: 'SOH',
                2: 'STX',
                3: 'ETX',
                4: 'EOT',
                5: 'ENQ',
                6: 'ACK',
                7: 'BEL',
                8: 'BS',
                9: 'HT',
                10: 'LF',
                11: 'VT',
                12: 'FF',
                13: 'CR',
                14: 'SO',
                15: 'SI',
                16: 'DLE',
                17: 'DC1',
                18: 'DC2',
                19: 'DC3',
                20: 'DC4',
                21: 'NAK',
                22: 'SYN',
                23: 'ETB',
                24: 'CAN',
                25: 'EM',
                26: 'SUB',
                27: 'ESC',
                28: 'FS',
                29: 'GS',
                30: 'RS',
                31: 'US',
            }.get(byte, f'CTRL-{byte}')
            
            print(f"  Position {i}: byte {byte} ({char_repr})")
            
            # Show context around this position
            start = max(0, i - 10)
            end = min(len(content), i + 10)
            context = content[start:end]
            print(f"    Context: {context}")
            
            # Try to decode as UTF-8 for display
            try:
                context_str = context.decode('utf-8')
                print(f"    Context (decoded): {repr(context_str)}")
            except UnicodeDecodeError:
                print(f"    Context (cannot decode): {context}")
            
            print()
    else:
        print("No control characters found")
    
    # Check for any problematic bytes
    print("Checking for potentially problematic bytes...")
    problematic_bytes = []
    for i, byte in enumerate(content):
        # Check for NULL bytes (0x00)
        if byte == 0:
            problematic_bytes.append((i, 'NULL'))
        # Check for other problematic bytes
        elif byte > 127 and byte < 160:  # Extended ASCII range
            problematic_bytes.append((i, f'Extended ASCII: {byte}'))
    
    if problematic_bytes:
        print(f"Found {len(problematic_bytes)} potentially problematic bytes:")
        for i, desc in problematic_bytes:
            print(f"  Position {i}: {desc}")
    else:
        print("No problematic bytes found")

if __name__ == '__main__':
    find_control_characters()
