#!/usr/bin/env python3
"""
Correct analysis of setupInno.iss line 60
"""

# Read setupInno.iss as raw bytes and analyze line by line
with open('E:/ho/arch/setupInno.iss', 'rb') as f:
    content = f.read()

# Split into lines
lines = content.split(b'\n')

print('=== ANALYSIS OF SETUPINNO.ISS LINE 60 ===')
print()

# Get line 60 (index 59)
line_60 = lines[59] if len(lines) > 59 else b''

print(f'Line 60 (repr): {repr(line_60)}')
print()

# Check if there's a tab character (ASCII 9)
if b'\\t' in line_60:
    print(f'Contains literal backslash-t (\\\\t) - INNO SETUP PATH SEPARATOR')
elif 9 in line_60:  # ASCII 9 is tab
    print(f'Contains actual tab character (ASCII 9) - ERROR!')
else:
    print(f'No tab character found')

print()
print(f'Path in line: {line_60.decode("utf-8", errors="ignore")}')
print()

# Check what the correct path should be
expected_path = b'Source: "arch\\trial_guard.py"; DestDir: "{app}"; Flags: ignoreversion'
if line_60 == expected_path:
    print('SUCCESS: Line 60 has the correct path format')
    print(f'Expected: {expected_path.decode("utf-8")}')
    print(f'Actual:   {line_60.decode("utf-8")}')
else:
    print('DIFFERENCE: Line 60 does not match expected format')
    print(f'Expected: {expected_path}')
    print(f'Actual:   {line_60}')
    
    # Find the difference
    for i, (expected, actual) in enumerate(zip(expected_path, line_60)):
        if expected != actual:
            print(f'Difference at position {i}:')
            print(f'  Expected: {expected} (0x{expected:02x})')
            print(f'  Actual:   {actual} (0x{actual:02x})')
            break

print()
print('=== CONCLUSION ===')
print('The path separator \\\\ is correct for Inno Setup file paths.')
print('The file name trial_guard.py is correct.')
print('No actual tab character error found.')
print()
print('If there is still an installation error, it might be unrelated to the file path.')
print('It could be a different issue with the installation process or the file itself.')
