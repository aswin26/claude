import os
import sys
from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_ENV_PATH)

def _get(key, default=""): return os.getenv(key, default).strip()
def _get_bool(key, default=False): return _get(key, str(default)).lower() in ("1","true","yes")
def _get_int(key, default=0):
    try: return int(_get(key, str(default)))
    except ValueError: return default

APPIAN_SOURCE_URL      = _get("APPIAN_SOURCE_URL").rstrip("/")
APPIAN_SOURCE_API_KEY  = _get("APPIAN_SOURCE_API_KEY")
APPIAN_TARGET_URL      = (_get("APPIAN_TARGET_URL") or APPIAN_SOURCE_URL).rstrip("/")
APPIAN_TARGET_API_KEY  = _get("APPIAN_TARGET_API_KEY") or APPIAN_SOURCE_API_KEY
APPIAN_APP_UUID        = _get("APPIAN_APP_UUID")
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

def validate(require_target=True):
    missing = []
    if not APPIAN_SOURCE_URL:     missing.append("APPIAN_SOURCE_URL")
    if not APPIAN_SOURCE_API_KEY: missing.append("APPIAN_SOURCE_API_KEY")
    if require_target:
        if not APPIAN_TARGET_URL:     missing.append("APPIAN_TARGET_URL")
        if not APPIAN_TARGET_API_KEY: missing.append("APPIAN_TARGET_API_KEY")
    if missing:
        print(f"\nERROR: Missing environment variables: {', '.join(missing)}")
        print("Copy scripts/.env.example to scripts/.env and fill in your values.")
        sys.exit(1)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(MODIFIED_DIR, exist_ok=True)

def print_summary():
    def mask(v): return "****" if len(v)<=8 else v[:4]+"****"+v[-4:] if v else "(not set)"
    print("\n--- Environment Configuration ---")
    print(f"  Source URL:      {APPIAN_SOURCE_URL or '(not set)'}")
    print(f"  Source API Key:  {mask(APPIAN_SOURCE_API_KEY)}")
    print(f"  Target URL:      {APPIAN_TARGET_URL or '(not set)'}")
    print(f"  Target API Key:  {mask(APPIAN_TARGET_API_KEY)}")
    if APPIAN_APP_UUID: print(f"  App UUID:        {APPIAN_APP_UUID}")
    if PROXIES:         print(f"  Proxies:         {PROXIES}")
    print(f"  Timeout:         {REQUEST_TIMEOUT}s  |  Deploy timeout: {DEPLOY_POLL_TIMEOUT}s")
    print(f"  Skip inspect:    {SKIP_INSPECT}  |  Auto approve: {AUTO_APPROVE}")
    print("---------------------------------\n")
