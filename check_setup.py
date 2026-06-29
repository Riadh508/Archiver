# Read the setupInno.iss file as bytes and check for issues
with open('E:/ho/arch/setupInno.iss', 'rb') as f:
    content = f.read()

# Look for the Source line with trial_guard.py
lines = content.split(b'\n')
for i, line in enumerate(lines, 1):
    if b'trial_guard' in line.lower():
        print(f"Line {i}: {line.decode('utf-8', errors='replace')}")
        # Check the exact bytes around this line
        print(f"  Hex: {line[:50].hex()}")
        print()