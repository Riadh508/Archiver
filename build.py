#!/usr/bin/env python3
"""
Archiver Build Helper Script
Assists with preparing the application for distribution
"""

import os
import sys
import shutil
from pathlib import Path

def main():
    print("Archiver Build Helper")
    print("=" * 30)
    
    project_root = Path(__file__).parent.absolute()
    print(f"Project root: {project_root}")
    
    # Check if we're in the right directory
    if not (project_root / "arch").exists():
        print("Error: 'arch' directory not found. Please run from project root.")
        return 1
    
    # Create dist directory
    dist_dir = project_root / "dist"
    dist_dir.mkdir(exist_ok=True)
    print(f"Created dist directory: {dist_dir}")
    
    # Copy essential files for distribution
    essential_files = [
        "arch/__main__.py",
        "arch/web.py", 
        "arch/core.py",
        "arch/ops.py",
        "arch/trial_guard.py",
        "arch/config.py",
        "arch/log.py",
        "arch/__init__.py"
    ]
    
    print("\nCopying essential files...")
    for file_rel in essential_files:
        src = project_root / file_rel
        dst = dist_dir / file_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  Copied: {file_rel}")
        else:
            print(f"  Warning: {file_rel} not found")
    
    # Copy tests for reference (optional)
    tests_dir = dist_dir / "tests"
    if (project_root / "tests").exists():
        shutil.copytree(project_root / "tests", tests_dir, dirs_exist_ok=True)
        print("  Copied: tests/")
    
    # Create a simple runner script
    runner_content = '''#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

if len(sys.argv) > 1 and sys.argv[1] == "web":
    from arch import web
    import sys
    host = "127.0.0.1"
    port = 8080
    # Parse simple args
    for i, arg in enumerate(sys.argv[2:], 2):
        if arg == "--host" and i+1 < len(sys.argv):
            host = sys.argv[i+1]
        elif arg == "--port" and i+1 < len(sys.argv):
            try:
                port = int(sys.argv[i+1])
            except ValueError:
                pass
    web.serve(host=host, port=port)
else:
    from arch.__main__ import main
    main()
'''
    
    runner_path = dist_dir / "run.py"
    with open(runner_path, 'w', encoding='utf-8') as f:
        f.write(runner_content)
    print(f"  Created: run.py")
    
    print("\nBuild preparation complete!")
    print(f"Distribution files ready in: {dist_dir}")
    print("\nTo test:")
    print(f"  CD {dist_dir}")
    print("  python run.py --help")
    print("  python run.py web")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())