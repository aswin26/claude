#!/usr/bin/env python3
"""
Set up Appian credentials by creating scripts/.env from the example template.

Usage:
    python scripts/setup_credentials.py
"""
import shutil
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
ENV_FILE    = SCRIPTS_DIR / ".env"
EXAMPLE     = SCRIPTS_DIR / ".env.example"

def main():
    if ENV_FILE.exists():
        print(f"  {ENV_FILE} already exists.")
        print(f"  Edit it directly to update your credentials.")
    else:
        shutil.copy(EXAMPLE, ENV_FILE)
        print(f"  Created {ENV_FILE}")
        print(f"  Open it and fill in APPIAN_DOMAIN and APPIAN_API_KEY.")

    print("\n  Then restart the web server for changes to take effect.")

if __name__ == "__main__":
    main()
