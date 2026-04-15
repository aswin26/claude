#!/usr/bin/env python3
"""
Securely save Appian credentials to ~/.appian/credentials.json

Credentials are stored outside the project directory so they are
never accidentally committed to git. The file is created with
mode 0600 (owner read/write only).

Usage:
    python scripts/setup_credentials.py
    python scripts/setup_credentials.py --show     # display current credentials
    python scripts/setup_credentials.py --clear    # delete saved credentials
"""
import os
import sys
import json
import stat
import getpass
import argparse

CREDS_FILE = os.path.expanduser("~/.appian/credentials.json")

def load():
    if os.path.isfile(CREDS_FILE):
        with open(CREDS_FILE) as f:
            return json.load(f)
    return {}

def save(data):
    os.makedirs(os.path.dirname(CREDS_FILE), exist_ok=True)
    with open(CREDS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(CREDS_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    print(f"\nCredentials saved to {CREDS_FILE} (mode 0600)")

def mask(v):
    if not v: return "(not set)"
    return v[:4] + "****" + v[-4:] if len(v) > 8 else "****"

def cmd_show():
    creds = load()
    if not creds:
        print("No credentials saved. Run setup_credentials.py to configure.")
        return
    print(f"\nSaved credentials ({CREDS_FILE}):")
    print(f"  APPIAN_URL:     {creds.get('APPIAN_URL', '(not set)')}")
    print(f"  APPIAN_API_KEY: {mask(creds.get('APPIAN_API_KEY', ''))}")
    if creds.get("APPIAN_APP_UUID"):
        print(f"  APPIAN_APP_UUID: {creds['APPIAN_APP_UUID']}")

def cmd_clear():
    if os.path.isfile(CREDS_FILE):
        os.remove(CREDS_FILE)
        print(f"Deleted {CREDS_FILE}")
    else:
        print("No credentials file found.")

def cmd_setup():
    existing = load()

    print("\n=== Appian Credentials Setup ===")
    print("Values in [brackets] are the current saved values. Press Enter to keep them.\n")

    url_default = existing.get("APPIAN_URL", "")
    url_prompt  = f"Appian URL [{url_default}]: " if url_default else "Appian URL (e.g. https://mysite.appiancloud.com): "
    url = input(url_prompt).strip().rstrip("/") or url_default

    key_hint   = mask(existing.get("APPIAN_API_KEY", ""))
    key_prompt = f"API Key [{key_hint}] (input hidden): " if existing.get("APPIAN_API_KEY") else "API Key (input hidden): "
    api_key = getpass.getpass(key_prompt).strip() or existing.get("APPIAN_API_KEY", "")

    uuid_default = existing.get("APPIAN_APP_UUID", "")
    uuid_prompt  = f"Default App UUID [{uuid_default}] (optional, press Enter to skip): " if uuid_default else "Default App UUID (optional, press Enter to skip): "
    app_uuid = input(uuid_prompt).strip() or uuid_default

    if not url or not api_key:
        print("\nERROR: Appian URL and API Key are required.")
        sys.exit(1)

    creds = {"APPIAN_URL": url, "APPIAN_API_KEY": api_key}
    if app_uuid:
        creds["APPIAN_APP_UUID"] = app_uuid

    save(creds)
    print(f"\n  Appian URL:     {url}")
    print(f"  Appian API Key: {mask(api_key)}")
    if app_uuid: print(f"  App UUID:       {app_uuid}")
    print("\nSetup complete.")
    print("  CLI:  python scripts/appian_workflow.py --list-apps")
    print("  Web:  cd web && uvicorn app:app --reload")

def main():
    p = argparse.ArgumentParser(description="Manage Appian credentials")
    p.add_argument("--show",  action="store_true", help="Show saved credentials")
    p.add_argument("--clear", action="store_true", help="Delete saved credentials")
    args = p.parse_args()

    if args.show:  cmd_show()
    elif args.clear: cmd_clear()
    else: cmd_setup()

if __name__ == "__main__":
    main()
