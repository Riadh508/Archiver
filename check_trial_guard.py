# Check the exact bytes in trial_guard.py
with open('E:/ho/arch/arch/trial_guard.py', 'rb') as f:
    content = f.read()

# Print first 100 bytes as hex
print("First 100 bytes (hex):")
print(content[:100].hex())
print()

# Print the raw content around the non-ASCII characters
content_str = content.decode('utf-8', errors='replace')
lines = content_str.split('\n')
for i, line in enumerate(lines[:30], 1):
    if any(ord(c) > 127 for c in line):
        print(f"Line {i} (hex for non-ASCII): {line.encode('utf-8').hex()}")