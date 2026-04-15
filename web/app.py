"""
Appian Dev Studio — FastAPI backend

Run:
    cd web
    uvicorn app:app --reload --port 8000

Then open http://localhost:8000
"""
import sys, os, json, uuid, asyncio, threading, traceback, io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import yaml

# ---- Path setup ----
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import config
from appian_client import AppianClient
from exporter import export_application
from modifier import apply_patches
from deployer import package_modified, inspect_before_deploy, deploy as do_deploy

# ---- App ----
app = FastAPI(title="Appian Dev Studio")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# job_id -> {queue, done, result, error}
_jobs: dict = {}


# ---- Stdout capture: routes script print() to SSE queue ----
class _LogCapture(io.RawIOBase):
    def __init__(self, q: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._q = q
        self._loop = loop
        self._buf = ""

    def write(self, s):
        if isinstance(s, bytes):
            s = s.decode("utf-8", errors="replace")
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                asyncio.run_coroutine_threadsafe(self._q.put(line), self._loop)
        return len(s)

    def flush(self):
        if self._buf.strip():
            asyncio.run_coroutine_threadsafe(self._q.put(self._buf), self._loop)
            self._buf = ""

    # Make it usable as a text stream wrapper
    def readable(self): return False
    def writable(self): return True


def _log(q, loop, msg):
    asyncio.run_coroutine_threadsafe(q.put(msg), loop)


def _finish(q, loop):
    asyncio.run_coroutine_threadsafe(q.put(None), loop)  # sentinel


# ---- Config reload ----
def _reload_config():
    """Re-read scripts/.env so changes take effect without restarting."""
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / "scripts" / ".env"
    load_dotenv(env_path, override=True)
    domain = os.getenv("APPIAN_DOMAIN", "")
    config.APPIAN_URL     = f"https://{domain}" if domain else ""
    config.APPIAN_API_KEY = os.getenv("APPIAN_API_KEY", "")


# ---- Pydantic models ----
class GenerateRequest(BaseModel):
    app_uuid: str
    requirement: str


class DeployRequest(BaseModel):
    app_uuid: str
    patches_yaml: str
    deploy_name: str = "Claude-generated deployment"


# ---- Routes ----

@app.get("/")
def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())


@app.get("/api/status")
def api_status():
    _reload_config()
    return {
        "appian_ok": bool(config.APPIAN_URL and config.APPIAN_API_KEY),
        "url":       config.APPIAN_URL or "",
    }


@app.get("/api/apps")
def api_list_apps():
    _reload_config()
    print(f"[api/apps] URL={config.APPIAN_URL!r} key_set={bool(config.APPIAN_API_KEY)}")
    if not (config.APPIAN_URL and config.APPIAN_API_KEY):
        raise HTTPException(400, "Appian credentials not configured. Edit scripts/.env and restart the server.")
    try:
        client = AppianClient(config.APPIAN_URL, config.APPIAN_API_KEY)
        apps = client.list_applications()
        print(f"[api/apps] response={apps}")
        return {"apps": apps}
    except Exception as e:
        print(f"[api/apps] ERROR: {e}")
        raise HTTPException(502, f"Could not connect to Appian: {e}")


@app.post("/api/generate")
async def api_generate(req: GenerateRequest):
    _reload_config()
    job_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = {"queue": q, "done": False, "result": None, "error": None}
    loop = asyncio.get_running_loop()
    threading.Thread(
        target=_bg_generate,
        args=(job_id, req.app_uuid, req.requirement, loop),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.post("/api/deploy")
async def api_deploy(req: DeployRequest):
    _reload_config()
    job_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = {"queue": q, "done": False, "result": None, "error": None}
    loop = asyncio.get_running_loop()
    threading.Thread(
        target=_bg_deploy,
        args=(job_id, req.app_uuid, req.patches_yaml, req.deploy_name, loop),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/stream")
async def api_stream(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "Job not found")

    async def events():
        q = _jobs[job_id]["queue"]
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30)
                if msg is None:
                    job = _jobs[job_id]
                    payload = json.dumps({
                        "type":   "done",
                        "result": job["result"],
                        "error":  job["error"],
                    })
                    yield f"data: {payload}\n\n"
                    break
                yield f"data: {json.dumps({'type': 'log', 'msg': msg})}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Background workers ----

def _bg_generate(job_id: str, app_uuid: str, requirement: str, loop: asyncio.AbstractEventLoop):
    job = _jobs[job_id]
    q   = job["queue"]
    cap = _LogCapture(q, loop)

    try:
        os.makedirs(config.EXPORT_DIR,   exist_ok=True)
        os.makedirs(config.MODIFIED_DIR, exist_ok=True)

        # STEP 1 — Export
        _log(q, loop, "── STEP 1: Exporting application ──────────────────────")
        client = AppianClient(config.APPIAN_URL, config.APPIAN_API_KEY)
        with redirect_stdout(cap), redirect_stderr(cap):
            extract_dir = export_application(client, app_uuid)

        # STEP 2 — Read files
        _log(q, loop, "\n── STEP 2: Reading exported objects ───────────────────")
        file_contents: dict[str, str] = {}
        for root, _, files in os.walk(extract_dir):
            for fname in files:
                full = os.path.join(root, fname)
                rel  = os.path.relpath(full, extract_dir).replace("\\", "/")
                try:
                    with open(full, encoding="utf-8", errors="ignore") as f:
                        file_contents[rel] = f.read()
                except OSError:
                    pass
        _log(q, loop, f"  {len(file_contents)} file(s) loaded")

        # Build Claude context (cap at ~80 k chars to stay well within token limit)
        files_ctx = ""
        total = 0
        for path, content in file_contents.items():
            snippet = content[:2500] + "\n[...truncated]" if len(content) > 2500 else content
            entry   = f"\n=== {path} ===\n{snippet}\n"
            if total + len(entry) > 80_000:
                break
            files_ctx += entry
            total += len(entry)

        # STEP 3 — Generate patches template
        _log(q, loop, "\n── STEP 3: Generating patches template ────────────────")
        file_list = "\n".join(f"  - {p}" for p in file_contents)
        patches_yaml = (
            f"# Requirement: {requirement}\n"
            f"#\n"
            f"# Exported files:\n"
            f"{file_list}\n"
            f"#\n"
            f"# Edit the patches below. Each patch targets one file.\n"
            f"# Use 'changes' for text replacement or 'xpath' for element value.\n"
            f"\n"
            f"patches:\n"
            f"  - file: \"path/to/file.xml\"\n"
            f"    changes:\n"
            f"      - find: \"exact text to find\"\n"
            f"        replace: \"replacement text\"\n"
            f"  # - file: \"path/to/file.xml\"\n"
            f"  #   xpath: \".//elementName\"\n"
            f"  #   new_value: \"new value\"\n"
        )
        _log(q, loop, "  Template ready — edit patches before deploying ✓")

        job["result"] = {
            "patches_yaml": patches_yaml,
            "file_count":   len(file_contents),
            "extract_dir":  extract_dir,
        }
        job["done"] = True

    except Exception as e:
        job["error"] = str(e)
        job["done"]  = True
        _log(q, loop, f"\nERROR: {e}")
    finally:
        _finish(q, loop)


def _bg_deploy(
    job_id: str,
    app_uuid: str,
    patches_yaml_str: str,
    deploy_name: str,
    loop: asyncio.AbstractEventLoop,
):
    job = _jobs[job_id]
    q   = job["queue"]
    cap = _LogCapture(q, loop)

    try:
        os.makedirs(config.EXPORT_DIR,   exist_ok=True)
        os.makedirs(config.MODIFIED_DIR, exist_ok=True)

        client = AppianClient(config.APPIAN_URL, config.APPIAN_API_KEY)

        # STEP 1 — Export
        _log(q, loop, "── STEP 1: Exporting application ──────────────────────")
        with redirect_stdout(cap), redirect_stderr(cap):
            extract_dir = export_application(client, app_uuid)

        # STEP 2 — Apply patches
        _log(q, loop, "\n── STEP 2: Applying patches ───────────────────────────")
        parsed = yaml.safe_load(patches_yaml_str)
        patches = parsed.get("patches", []) if parsed else []
        _log(q, loop, f"  {len(patches)} patch(es) to apply")
        with redirect_stdout(cap), redirect_stderr(cap):
            modified_dir = apply_patches(extract_dir, patches)

        # STEP 3 — Package
        _log(q, loop, "\n── STEP 3: Packaging ──────────────────────────────────")
        with redirect_stdout(cap), redirect_stderr(cap):
            pkg = package_modified(modified_dir)

        # STEP 4 — Inspect (optional)
        if not config.SKIP_INSPECT:
            _log(q, loop, "\n── STEP 4: Inspecting ─────────────────────────────────")
            with redirect_stdout(cap), redirect_stderr(cap):
                insp = inspect_before_deploy(client, pkg)
            if insp.get("status") == "FAILED":
                raise RuntimeError("Pre-deployment inspection failed — deployment aborted.")

        # STEP 5 — Deploy
        _log(q, loop, f"\n── STEP 5: Deploying → {config.APPIAN_URL} ─────────────")
        with redirect_stdout(cap), redirect_stderr(cap):
            result = do_deploy(client, pkg, deploy_name, "Deployed via Appian Dev Studio")

        ok  = result.get("status") == "COMPLETED"
        uid = result.get("uuid", "N/A")
        _log(q, loop, "\n" + "═" * 54)
        _log(q, loop, "✓  DEPLOYMENT SUCCESSFUL" if ok else f"✗  DEPLOYMENT FAILED  {result.get('problemMessage','')}")
        _log(q, loop, f"   UUID: {uid}")

        job["result"] = {"ok": ok, "status": result.get("status"), "uuid": uid}
        job["done"]   = True

    except Exception as e:
        job["error"] = str(e)
        job["done"]  = True
        _log(q, loop, f"\nERROR: {e}")
    finally:
        _finish(q, loop)


if __name__ == "__main__":
    import uvicorn
    print("\nAppian Dev Studio")
    print("Open http://localhost:8000\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
