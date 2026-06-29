# Let's check the exact content of the setup script line by line
with open('E:/ho/arch/setupInno.iss', 'rb') as f:
    content = f.read()

# Print line 60 as raw bytes
lines = content.split(b'\n')
line_60 = lines[59] if len(lines) > 59 else b''
print(f"Line 60 (hex): {line_60.hex()}")
print(f"Line 60 (raw): {line_60}")
print()

# Try to decode it
for encoding in ['utf-8', 'latin-1', 'cp1252']:
    try:
        decoded = line_60.decode(encoding)
        print(f"Decoded as {encoding}: {decoded}")
        
        # Check if it contains tab
        if '\t' in decoded:
            print(f"  ERROR: Contains TAB character!")
        elif 'trial_guard' in decoded.lower():
            print(f"  OK: Contains correct filename")
        else:
            print(f"  WARNING: Contains neither tab nor correct filename")
            
    except UnicodeDecodeError:
        print(f"Cannot decode as {encoding}")
print()