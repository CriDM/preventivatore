#!/usr/bin/env python3
import re
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "version.py"

def bump_patch():
    if not VERSION_FILE.exists():
        VERSION_FILE.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

    content = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"', content)
    if match:
        major, minor, patch = match.groups()
        new_patch = int(patch) + 1
        new_version = f"{major}.{minor}.{new_patch}"
        new_content = f'__version__ = "{new_version}"\n'
        VERSION_FILE.write_text(new_content, encoding="utf-8")
        print(f"Version bumped to v{new_version}")
        return new_version
    else:
        print("Could not parse version string in version.py")
        sys.exit(1)

if __name__ == "__main__":
    bump_patch()
