# Read setupInno.iss and check for potential path issues
with open('E:/ho/arch/setupInno.iss', 'rb') as f:
    content = f.read()

# Decode and check for problematic characters
text = content.decode('utf-8', errors='ignore')
lines = text.split('\n')

print('Checking for potential path issues...')
for i, line in enumerate(lines, 1):
    if 'trial_guard' in line.lower():
        print(f'Line {i}: {line}')
        
        # Check if the line has any obvious issues
        if line.count('\\') > 2:  # More than 2 backslashes might indicate an issue
            print(f'  Warning: More than 2 backslashes in line {i}')
            
        # Check for tab characters by looking at raw bytes
        if i <= len(lines):
            raw_line = lines[i-1]  # lines is 0-indexed
            if '\t' in raw_line:
                print(f'  ERROR: Tab character found in line {i}!')

print('Check complete.')