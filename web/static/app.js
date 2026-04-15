"use strict";

// ── DOM refs ──────────────────────────────────────────────────────────────────
const appSelect   = document.getElementById("app-select");
const requirement = document.getElementById("requirement");
const patchesYaml = document.getElementById("patches-yaml");
const deployName  = document.getElementById("deploy-name");
const btnGenerate = document.getElementById("btn-generate");
const btnDeploy   = document.getElementById("btn-deploy");
const logOutput   = document.getElementById("log-output");
const statusDot   = document.getElementById("status-dot");
const statusText  = document.getElementById("status-text");
const jobBadge    = document.getElementById("job-status");
const btnClear    = document.getElementById("btn-clear");
const appError    = document.getElementById("app-error");

// ── Logging ───────────────────────────────────────────────────────────────────
function clearLog() {
  logOutput.innerHTML = "";
}

function logLine(msg, cls = "") {
  // Remove placeholder if present
  const empty = logOutput.querySelector(".log-empty");
  if (empty) empty.remove();

  const div = document.createElement("div");
  div.className = "line" + (cls ? " " + cls : "");
  div.textContent = msg;
  logOutput.appendChild(div);
  logOutput.scrollTop = logOutput.scrollHeight;
}

function classifyLine(msg) {
  const m = msg.trim();
  if (m.startsWith("──") || m.startsWith("===") || m.startsWith("═"))
    return "section";
  if (/error|failed|exception/i.test(m))  return "error";
  if (/warn/i.test(m))                     return "warn";
  if (/✓|success|complete|deployed/i.test(m)) return "success";
  if (/skipped|not found/i.test(m))        return "warn";
  return "";
}

btnClear.onclick = clearLog;

// ── Job badge ─────────────────────────────────────────────────────────────────
function setBadge(state, label) {
  jobBadge.textContent = label;
  jobBadge.className   = "job-badge " + state;
  jobBadge.classList.remove("hidden");
}
function hideBadge() { jobBadge.classList.add("hidden"); }

// ── Status check ─────────────────────────────────────────────────────────────
async function checkStatus() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();

    statusDot.className = "dot " + (s.appian_ok ? "ok" : "err");

    if (s.appian_ok) {
      const host = s.url ? new URL(s.url).hostname : "configured";
      statusText.textContent = `Ready — ${host}`;
    } else {
      statusText.textContent = "Not configured: Appian credentials";
    }

    return s;
  } catch {
    statusDot.className = "dot err";
    statusText.textContent = "Server unreachable";
    return null;
  }
}

// ── Load app list ─────────────────────────────────────────────────────────────
async function loadApps() {
  appSelect.disabled = true;
  appSelect.innerHTML = '<option value="">— loading —</option>';
  appError.classList.add("hidden");

  try {
    const r = await fetch("/api/apps");
    if (!r.ok) {
      const d = await r.json();
      throw new Error(d.detail || r.statusText);
    }
    const { apps } = await r.json();

    appSelect.innerHTML = '<option value="">— select application —</option>';
    (apps || []).forEach(a => {
      const o = document.createElement("option");
      o.value       = a.uuid || a.id || "";
      o.textContent = a.name || a.uuid || "(unnamed)";
      appSelect.appendChild(o);
    });
    appSelect.disabled = false;
  } catch (e) {
    appError.textContent = `Could not load apps: ${e.message}`;
    appError.classList.remove("hidden");
    appSelect.innerHTML = '<option value="">— unavailable —</option>';
  }
}

// ── Enable/disable generate button ───────────────────────────────────────────
function syncGenerateBtn() {
  btnGenerate.disabled = !appSelect.value || !requirement.value.trim();
}
appSelect.addEventListener("change", syncGenerateBtn);
requirement.addEventListener("input",  syncGenerateBtn);

// ── SSE job streaming ─────────────────────────────────────────────────────────
function streamJob(jobId, onDone) {
  const es = new EventSource(`/api/jobs/${jobId}/stream`);

  es.onmessage = e => {
    const data = JSON.parse(e.data);

    if (data.type === "log") {
      logLine(data.msg, classifyLine(data.msg));
    } else if (data.type === "done") {
      es.close();
      onDone(data.result, data.error);
    }
    // "ping" — ignore
  };

  es.onerror = () => {
    es.close();
    logLine("Connection lost — check if the server is still running.", "error");
    onDone(null, "SSE connection error");
  };

  return es;
}

// ── Generate ──────────────────────────────────────────────────────────────────
btnGenerate.addEventListener("click", async () => {
  const app_uuid    = appSelect.value;
  const req         = requirement.value.trim();
  if (!app_uuid || !req) return;

  // Reset UI
  clearLog();
  patchesYaml.value = "";
  btnDeploy.disabled = true;
  btnGenerate.disabled = true;
  btnGenerate.innerHTML =
    '<span class="spinning">⟳</span> Generating…';
  setBadge("running", "● Generating");

  try {
    const r = await fetch("/api/generate", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ app_uuid, requirement: req }),
    });
    if (!r.ok) throw new Error((await r.json()).detail);
    const { job_id } = await r.json();

    streamJob(job_id, (result, error) => {
      // Restore button
      btnGenerate.disabled = false;
      btnGenerate.innerHTML =
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>'
        + " Inspect & Generate Template";

      if (error) {
        setBadge("failed", "✗ Failed");
        logLine(`\nGeneration error: ${error}`, "error");
      } else if (result?.patches_yaml) {
        setBadge("done", "✓ Done");
        patchesYaml.value  = result.patches_yaml;
        btnDeploy.disabled = false;
        logLine(`\n${result.file_count} file(s) analysed.`, "info");
        logLine("Patches ready — review and click Deploy.", "success");
      } else {
        setBadge("failed", "✗ No output");
        logLine("Claude returned no patches.", "warn");
      }
    });
  } catch (e) {
    setBadge("failed", "✗ Error");
    logLine(`Request failed: ${e.message}`, "error");
    btnGenerate.disabled = false;
    btnGenerate.innerHTML =
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>'
      + " Inspect & Generate Template";
  }
});

// ── Deploy ────────────────────────────────────────────────────────────────────
btnDeploy.addEventListener("click", async () => {
  const app_uuid    = appSelect.value;
  const yamlContent = patchesYaml.value.trim();
  if (!app_uuid || !yamlContent) return;

  clearLog();
  btnDeploy.disabled = true;
  btnDeploy.innerHTML = '<span class="spinning">⟳</span> Deploying…';
  setBadge("running", "● Deploying");

  try {
    const r = await fetch("/api/deploy", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        app_uuid,
        patches_yaml: yamlContent,
        deploy_name:  deployName.value.trim() || "Claude-generated deployment",
      }),
    });
    if (!r.ok) throw new Error((await r.json()).detail);
    const { job_id } = await r.json();

    streamJob(job_id, (result, error) => {
      btnDeploy.disabled = false;
      btnDeploy.innerHTML =
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 2L11 13"/><path d="M22 2L15 22 11 13 2 9l20-7z"/></svg>'
        + " Deploy";

      if (error) {
        setBadge("failed", "✗ Failed");
        logLine(`\nDeploy error: ${error}`, "error");
      } else if (result?.ok) {
        setBadge("done", "✓ Deployed");
        logLine(`\nDeployment UUID: ${result.uuid}`, "info");
      } else {
        setBadge("failed", `✗ ${result?.status || "Failed"}`);
        btnDeploy.disabled = false;
      }
    });
  } catch (e) {
    setBadge("failed", "✗ Error");
    logLine(`Request failed: ${e.message}`, "error");
    btnDeploy.disabled = false;
    btnDeploy.innerHTML =
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 2L11 13"/><path d="M22 2L15 22 11 13 2 9l20-7z"/></svg>'
      + " Deploy";
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  const s = await checkStatus();
  if (s?.appian_ok) {
    await loadApps();
  } else {
    logLine("Credentials not configured.", "warn");
    logLine("Edit scripts/.env with your APPIAN_DOMAIN and APPIAN_API_KEY.", "muted");
    logLine("Then restart the server and refresh this page.", "muted");
  }
})();
