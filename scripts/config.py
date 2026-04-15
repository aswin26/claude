import os
import sys
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

def _get(key, default=""):
    return os.getenv(key, default) or default

def _get_bool(key, default=False):
    return str(_get(key, str(default))).strip().lower() in ("1", "true", "yes")

def _get_int(key, default=0):
    try: return int(_get(key, str(default)))
    except ValueError: return default

APPIAN_DOMAIN = _get("APPIAN_DOMAIN")
APPIAN_URL    = f"https://{APPIAN_DOMAIN}" if APPIAN_DOMAIN else ""
APPIAN_API_KEY  = _get("APPIAN_API_KEY")
APPIAN_APP_UUID = _get("APPIAN_APP_UUID")

APPIAN_DEPLOY_NAME        = _get("APPIAN_DEPLOY_NAME", "Automated Deployment")
APPIAN_DEPLOY_DESCRIPTION = _get("APPIAN_DEPLOY_DESCRIPTION", "Deployed via appian_workflow.py")

DOWNLOAD_DIR         = _get("APPIAN_DOWNLOAD_DIR", "./downloads")
DEPLOY_POLL_INTERVAL = _get_int("APPIAN_POLL_INTERVAL", 5)
DEPLOY_POLL_TIMEOUT  = _get_int("APPIAN_MAX_POLL_TRIES", 60) * _get_int("APPIAN_POLL_INTERVAL", 5)

REQUEST_TIMEOUT = _get_int("REQUEST_TIMEOUT", 60)
SKIP_INSPECT    = _get_bool("SKIP_INSPECT", False)
AUTO_APPROVE    = _get_bool("AUTO_APPROVE", False)

WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), "..", "workspace")
EXPORT_DIR    = os.path.join(WORKSPACE_DIR, "export")
MODIFIED_DIR  = os.path.join(WORKSPACE_DIR, "modified")

def validate():
    missing = []
    if not APPIAN_DOMAIN:  missing.append("APPIAN_DOMAIN")
    if not APPIAN_API_KEY: missing.append("APPIAN_API_KEY")
    if missing:
        print(f"\nERROR: Missing in scripts/.env: {', '.join(missing)}")
        print("Copy scripts/.env.example to scripts/.env and fill in values.")
        sys.exit(1)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(MODIFIED_DIR, exist_ok=True)
