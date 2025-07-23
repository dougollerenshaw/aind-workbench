#!/usr/bin/env python3
"""
Main acquisition generation script.

Currently just calls the JHU ephys script. In the future, we can add
routing logic to call different scripts for different session types.
"""

import subprocess
import sys
from pathlib import Path

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()

def main():
    """Main function - currently just calls JHU ephys script."""
    # For now, just call the JHU ephys script with all arguments passed through
    cmd = [sys.executable, str(SCRIPT_DIR / "make_jhu_ephys_acquisitions.py")] + sys.argv[1:]
    
    print("Calling make_jhu_ephys_acquisitions.py with arguments:", sys.argv[1:])
    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()