#!/usr/bin/env python3
"""
Fix arch.ico to include multiple resolutions for better compatibility
Run this script to regenerate the icon before building the installer
"""

import struct
import zlib
import io

def create_png(width, height, r, g, b, a=255):
    """Create a simple PNG icon with a gradient design"""
    import struct, zlib
    
    # Create RGBA pixel data
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # filter byte
        for x in range(width):
            # Gradient from center
            cx, cy = width/2, height/2
            dx, dy = x - cx, y - cy
            dist = (dx*dx + dy*dy) ** 0.5
            max_dist = (cx*cx + cy*cy) ** 0.5
            
            # Arch symbol: outer circle
            if dist < max_dist * 0.9:
                # Inner circle (hole)
                if dist > max_dist * 0.3:
                    # Gradient fill
                    t = dist / max_dist
                    rr = int(r * (1-t) + 255 * t)
                    gg = int(g * (1-t) + 255 * t)
                    bb = int(b * (1-t) + 255 * t)
                    raw_data += bytes([rr, gg, bb, 255])
                else:
                    raw_data += bytes([255, 255, 255, 0])  # transparent center
            else:
                raw_data += bytes([255, 255, 255, 0])  # transparent outside
    
    # Build PNG
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc
    
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    compressed = zlib.compress(raw_data)
    
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')

def create_ico_with_sizes(sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]):
    """Create a multi-resolution ICO file"""
    png_data = {}
    for w, h in sizes:
        png_data[(w,h)] = create_png(w, h, 70, 130, 180)  # Steel blue gradient
    
    count = len(png_data)
    header = struct.pack('<HHH', 0, 1, count)
    
    entries = b''
    offset = 6 + count * 16
    
    for (w, h) in sizes:
        data = png_data[(w, h)]
        iw = w if w < 256 else 0
        ih = h if h < 256 else 0
        entry = struct.pack('<BBBBHHII', iw, ih, 0, 0, 1, 32, len(data), offset)
        entries += entry
        offset += len(data)
    
    icon_data = header + entries
    for (w, h) in sizes:
        icon_data += png_data[(w, h)]
    
    return icon_data

if __name__ == '__main__':
    import sys
    output_path = sys.argv[1] if len(sys.argv) > 1 else 'arch.ico'
    
    print(f"Generating multi-resolution icon: {output_path}")
    ico_data = create_ico_with_sizes()
    
    with open(output_path, 'wb') as f:
        f.write(ico_data)
    
    print(f"Created icon with {len(ico_data)} bytes")
    print(f"Includes: 16x16, 32x32, 48x48, 64x64, 128x128, 256x256")
    print("Done!")