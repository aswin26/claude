"""
Appian Dev Studio — FastAPI backend

Run:
    cd web
    uvicorn app:app --reload --port 8000

Then open http://localhost:8000
"""
import sys, os, json, uuid, asyncio, threading, traceback, io, zipfile, tempfile
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
from agents import MultiAgentOrchestrator

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
                asyncio.run_coroutine_threadsafe(self._q.put(("log", line)), self._loop)
        return len(s)

    def flush(self):
        if self._buf.strip():
            asyncio.run_coroutine_threadsafe(self._q.put(("log", self._buf)), self._loop)
            self._buf = ""

    def readable(self): return False
    def writable(self): return True


def _log(q, loop, msg):
    asyncio.run_coroutine_threadsafe(q.put(("log", msg)), loop)


def _event(q, loop, payload: dict):
    """Emit a structured workflow event (stage updates, final objects, etc.)."""
    asyncio.run_coroutine_threadsafe(q.put(("event", payload)), loop)


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
    config.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ---- Pydantic models ----
class WorkflowRequest(BaseModel):
    requirement: str
    app_uuid: str = ""          # optional — skip export if blank


class DeployObjectsRequest(BaseModel):
    objects: list               # list of {type, name, filename, content, ...}
    deploy_name: str = "AI-generated deployment"
    app_uuid: str = ""


# ---- Routes ----

@app.get("/")
def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())


@app.get("/api/status")
def api_status():
    _reload_config()
    return {
        "appian_ok":    bool(config.APPIAN_URL and config.APPIAN_API_KEY),
        "anthropic_ok": bool(config.ANTHROPIC_API_KEY),
        "url":          config.APPIAN_URL or "",
    }


@app.get("/api/apps")
def api_list_apps():
    _reload_config()
    if not (config.APPIAN_URL and config.APPIAN_API_KEY):
        raise HTTPException(400, "Appian credentials not configured.")
    try:
        client = AppianClient(config.APPIAN_URL, config.APPIAN_API_KEY)
        apps = client.list_applications()
        return {"apps": apps}
    except Exception as e:
        raise HTTPException(502, f"Could not connect to Appian: {e}")


@app.post("/api/workflow")
async def api_workflow(req: WorkflowRequest):
    """
    Start the multi-agent workflow (Designer → Developer → Verify → Test).
    Returns a job_id; stream progress via /api/jobs/{job_id}/stream.
    """
    _reload_config()
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY not configured in scripts/.env")

    job_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = {"queue": q, "done": False, "result": None, "error": None}
    loop = asyncio.get_running_loop()
    threading.Thread(
        target=_bg_workflow,
        args=(job_id, req.requirement, req.app_uuid, loop),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.post("/api/deploy-objects")
async def api_deploy_objects(req: DeployObjectsRequest):
    """
    Deploy only the specific objects produced by the multi-agent workflow.
    Creates a minimal Appian package containing just those objects.
    """
    _reload_config()
    if not (config.APPIAN_URL and config.APPIAN_API_KEY):
        raise HTTPException(400, "Appian credentials not configured.")

    job_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = {"queue": q, "done": False, "result": None, "error": None}
    loop = asyncio.get_running_loop()
    threading.Thread(
        target=_bg_deploy_objects,
        args=(job_id, req.objects, req.deploy_name, loop),
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
                item = await asyncio.wait_for(q.get(), timeout=30)
                if item is None:
                    job = _jobs[job_id]
                    payload = json.dumps({
                        "type":   "done",
                        "result": job["result"],
                        "error":  job["error"],
                    })
                    yield f"data: {payload}\n\n"
                    break
                kind, data = item
                if kind == "log":
                    yield f"data: {json.dumps({'type': 'log', 'msg': data})}\n\n"
                elif kind == "event":
                    yield f"data: {json.dumps({'type': 'workflow_event', **data})}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Background workers ----

def _bg_workflow(
    job_id: str,
    requirement: str,
    app_uuid: str,
    loop: asyncio.AbstractEventLoop,
):
    """
    Runs the full multi-agent workflow:
      1. (Optional) export Appian app to gather existing object context
      2. Designer Agent  — design spec
      3. Developer Agent — implement objects
      4. Designer Agent  — verify implementation
      5. Tester Agent    — unit tests + deployment readiness
    Only new / modified objects land in the final result.
    """
    job = _jobs[job_id]
    q   = job["queue"]
    cap = _LogCapture(q, loop)

    try:
        existing_objects: dict = {}
        existing_content: dict = {}

        # ── Step 1: export (optional) ────────────────────────────────────────
        if app_uuid and config.APPIAN_URL and config.APPIAN_API_KEY:
            _log(q, loop, "── Exporting application for context ──────────────────")
            try:
                client = AppianClient(config.APPIAN_URL, config.APPIAN_API_KEY)
                with redirect_stdout(cap), redirect_stderr(cap):
                    extract_dir = export_application(client, app_uuid)

                # Categorise objects by type
                for root, _, files in os.walk(extract_dir):
                    for fname in files:
                        full = os.path.join(root, fname)
                        rel  = os.path.relpath(full, extract_dir).replace("\\", "/")
                        parts = rel.split("/")
                        obj_type = parts[0] if len(parts) == 1 else parts[0]
                        existing_objects.setdefault(obj_type, []).append(rel)

                # Read content (capped at ~80 k chars total)
                total = 0
                for root, _, files in os.walk(extract_dir):
                    for fname in files:
                        if total > 80_000:
                            break
                        full = os.path.join(root, fname)
                        rel  = os.path.relpath(full, extract_dir).replace("\\", "/")
                        try:
                            with open(full, encoding="utf-8", errors="ignore") as f:
                                body = f.read()
                            snippet = body[:2500] if len(body) > 2500 else body
                            existing_content[rel] = snippet
                            total += len(snippet)
                        except OSError:
                            pass

                _log(q, loop,
                     f"  Loaded {sum(len(v) for v in existing_objects.values())} existing object(s)")
            except Exception as exc:
                _log(q, loop, f"  Export skipped (not critical): {exc}")
        else:
            _log(q, loop, "── No Appian connection — running without existing object context ──")

        # ── Steps 2-5: multi-agent workflow ──────────────────────────────────
        _log(q, loop, "\n── Starting Multi-Agent AI Workflow ───────────────────")

        def on_agent_event(ev: dict):
            # Forward structured event to SSE queue
            _event(q, loop, ev)
            # Also write a human-readable log line
            status_icon = {"start": "⏳", "running": "⏳", "done": "✓", "error": "✗"}.get(
                ev.get("status", ""), "·"
            )
            _log(q, loop, f"  [{ev.get('stage','').upper()}] {status_icon} {ev.get('message','')}")

        orchestrator = MultiAgentOrchestrator(config.ANTHROPIC_API_KEY)
        workflow_result = orchestrator.run_workflow(
            requirement=requirement,
            existing_objects=existing_objects,
            existing_objects_content=existing_content,
            on_event=on_agent_event,
        )

        new_count  = len(workflow_result.get("new_objects", []))
        mod_count  = len(workflow_result.get("modified_objects", []))
        ready      = workflow_result.get("ready_for_deployment", False)
        test_sum   = workflow_result.get("test_summary", {})

        _log(q, loop, "\n" + "═" * 54)
        _log(q, loop, f"✓  Workflow complete — {new_count} new, {mod_count} modified object(s)")
        _log(q, loop, f"   Tests: {test_sum.get('passed',0)}/{test_sum.get('total_tests',0)} passed")
        _log(q, loop, f"   {'Ready for deployment ✓' if ready else 'Review issues before deploying ✗'}")

        job["result"] = workflow_result
        job["done"]   = True

    except Exception as e:
        job["error"] = str(e)
        job["done"]  = True
        _log(q, loop, f"\nERROR: {e}\n{traceback.format_exc()}")
    finally:
        _finish(q, loop)


def _bg_deploy_objects(
    job_id: str,
    objects: list,
    deploy_name: str,
    loop: asyncio.AbstractEventLoop,
):
    """
    Package and deploy only the supplied objects (new/modified) to Appian.
    Creates a minimal ZIP containing only those files + a package manifest.
    """
    job = _jobs[job_id]
    q   = job["queue"]
    cap = _LogCapture(q, loop)

    try:
        _log(q, loop, f"── Packaging {len(objects)} object(s) ─────────────────────")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write each object to its path inside the temp dir
            for obj in objects:
                filename = obj.get("filename") or f"{obj.get('type','Objects')}/{obj.get('name','obj')}.xml"
                dest = os.path.join(tmpdir, filename)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                content = obj.get("content") or obj.get("modified_content", "")
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(content)
                _log(q, loop, f"  ✓ {filename}")

            # Build ZIP in memory
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(tmpdir):
                    for fname in files:
                        full = os.path.join(root, fname)
                        arcname = os.path.relpath(full, tmpdir).replace("\\", "/")
                        zf.write(full, arcname)
            pkg_bytes = buf.getvalue()
            _log(q, loop, f"  Package size: {len(pkg_bytes):,} bytes")

            # Deploy
            client = AppianClient(config.APPIAN_URL, config.APPIAN_API_KEY)

            if not config.SKIP_INSPECT:
                _log(q, loop, "\n── Inspecting package ─────────────────────────────────")
                with redirect_stdout(cap), redirect_stderr(cap):
                    insp = inspect_before_deploy(client, pkg_bytes)
                if insp.get("status") == "FAILED":
                    raise RuntimeError("Pre-deployment inspection failed.")

            _log(q, loop, f"\n── Deploying → {config.APPIAN_URL} ─────────────────────")
            with redirect_stdout(cap), redirect_stderr(cap):
                result = do_deploy(client, pkg_bytes, deploy_name, "Deployed via Appian Dev Studio")

            ok  = result.get("status") == "COMPLETED"
            uid = result.get("uuid", "N/A")
            _log(q, loop, "\n" + "═" * 54)
            _log(q, loop, "✓  DEPLOYMENT SUCCESSFUL" if ok else
                 f"✗  DEPLOYMENT FAILED — {result.get('problemMessage', '')}")
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
