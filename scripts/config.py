import os
import sys
import json
from dotenv import load_dotenv

# Credentials are loaded from ~/.appian/credentials.json (preferred, secure)
# with fallback to scripts/.env (for CI or legacy use)
_CREDS_FILE = os.path.expanduser("~/.appian/credentials.json")
_ENV_PATH   = os.path.join(os.path.dirname(__file__), ".env")

def _load_credentials():
    """Load from secure credentials file, fallback to .env."""
    if os.path.isfile(_CREDS_FILE):
        try:
            with open(_CREDS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    load_dotenv(_ENV_PATH)
    return {}

_creds = _load_credentials()

def _get(key, default=""):
    return _creds.get(key) or os.getenv(key, default) or default

def _get_bool(key, default=False):
    return str(_get(key, str(default))).strip().lower() in ("1", "true", "yes")

def _get_int(key, default=0):
    try: return int(_get(key, str(default)))
    except ValueError: return default

APPIAN_URL     = _get("APPIAN_URL").rstrip("/")
APPIAN_API_KEY = _get("APPIAN_API_KEY")
APPIAN_APP_UUID = _get("APPIAN_APP_UUID")
APPIAN_DEPLOY_NAME     = _get("APPIAN_DEPLOY_NAME", "Automated Deployment")
APPIAN_DEPLOY_DESCRIPTION = _get("APPIAN_DEPLOY_DESCRIPTION", "Deployed via appian_workflow.py")

HTTP_PROXY  = _get("HTTP_PROXY")
HTTPS_PROXY = _get("HTTPS_PROXY")
PROXIES = {}
if HTTP_PROXY:  PROXIES["http"]  = HTTP_PROXY
if HTTPS_PROXY: PROXIES["https"] = HTTPS_PROXY

REQUEST_TIMEOUT      = _get_int("REQUEST_TIMEOUT", 60)
DEPLOY_POLL_INTERVAL = _get_int("DEPLOY_POLL_INTERVAL", 10)
DEPLOY_POLL_TIMEOUT  = _get_int("DEPLOY_POLL_TIMEOUT", 600)
SKIP_INSPECT         = _get_bool("SKIP_INSPECT", False)
AUTO_APPROVE         = _get_bool("AUTO_APPROVE", False)

WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), "..", "workspace")
EXPORT_DIR    = os.path.join(WORKSPACE_DIR, "export")
MODIFIED_DIR  = os.path.join(WORKSPACE_DIR, "modified")

def validate():
    missing = []
    if not APPIAN_URL:     missing.append("APPIAN_URL")
    if not APPIAN_API_KEY: missing.append("APPIAN_API_KEY")
    if missing:
        print(f"\nERROR: Missing credentials: {', '.join(missing)}")
        print("Run:  python scripts/setup_credentials.py")
        sys.exit(1)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(MODIFIED_DIR, exist_ok=True)

def print_summary():
    def mask(v): return "****" if len(v) <= 8 else v[:4] + "****" + v[-4:] if v else "(not set)"
    source = "credentials file" if os.path.isfile(_CREDS_FILE) else ".env file"
    print(f"\n--- Appian Environment ({source}) ---")
    print(f"  URL:     {APPIAN_URL or '(not set)'}")
    print(f"  API Key: {mask(APPIAN_API_KEY)}")
    if APPIAN_APP_UUID: print(f"  App UUID: {APPIAN_APP_UUID}")
    if PROXIES:         print(f"  Proxies:  {PROXIES}")
    print(f"  Timeout: {REQUEST_TIMEOUT}s  |  Deploy timeout: {DEPLOY_POLL_TIMEOUT}s")
    print(f"  Skip inspect: {SKIP_INSPECT}  |  Auto approve: {AUTO_APPROVE}")
    print("--------------------------------------\n")
