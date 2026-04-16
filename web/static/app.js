"use strict";

// ── DOM refs ──────────────────────────────────────────────────────────────────
const appSelect   = document.getElementById("app-select");
const requirement = document.getElementById("requirement");
const btnRun      = document.getElementById("btn-run");
const btnClear    = document.getElementById("btn-clear");
const btnDeploy   = document.getElementById("btn-deploy");
const deployName  = document.getElementById("deploy-name");
const logOutput   = document.getElementById("log-output");
const jobBadge    = document.getElementById("job-status");
const appError    = document.getElementById("app-error");
const stagesEl    = document.getElementById("stages");
const objectsPanel    = document.getElementById("objects-panel");
const objectsEmpty    = document.getElementById("objects-empty");
const newSection      = document.getElementById("new-objects-section");
const modSection      = document.getElementById("modified-objects-section");
const newList         = document.getElementById("new-objects-list");
const modList         = document.getElementById("modified-objects-list");
const newCount        = document.getElementById("new-objects-count");
const modCount        = document.getElementById("modified-objects-count");
const objectsCount    = document.getElementById("objects-count");
const tabObjects      = document.getElementById("tab-objects");
const testSummaryBar  = document.getElementById("test-summary-bar");
const testPassed      = document.getElementById("test-passed");
const testFailed      = document.getElementById("test-failed");
const testWarn        = document.getElementById("test-warn");
const deployReadiness = document.getElementById("deploy-readiness");
const deployStrip     = document.getElementById("deploy-strip");
const noAppianNote    = document.getElementById("no-appian-note");
const dotAppian       = document.getElementById("dot-appian");
const textAppian      = document.getElementById("text-appian");
const textClaude      = document.getElementById("text-claude");

// State
let _workflowResult = null;   // final workflow result
let _appianReady    = false;  // Appian connected

// ── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    if (btn.disabled) return;
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-panel-${btn.dataset.tab}`).classList.add("active");
  });
});

// ── Logging ───────────────────────────────────────────────────────────────────
function clearLog() {
  logOutput.innerHTML = "";
}

function logLine(msg, cls = "") {
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
  if (m.startsWith("──") || m.startsWith("===") || m.startsWith("═")) return "section";
  if (/error|failed|exception/i.test(m)) return "error";
  if (/warn/i.test(m))                   return "warn";
  if (/✓|success|complete|ready/i.test(m)) return "success";
  if (/waiting|skip/i.test(m))           return "muted";
  return "";
}

btnClear.onclick = () => {
  clearLog();
  resetStages();
  resetObjects();
};

// ── Badge ─────────────────────────────────────────────────────────────────────
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

    _appianReady = s.appian_ok;

    dotAppian.className = "dot " + (s.appian_ok ? "ok" : "err");
    if (s.appian_ok) {
      const host = s.url ? new URL(s.url).hostname : "configured";
      textAppian.textContent = host;
    } else {
      textAppian.textContent = "Appian not configured";
    }

    textClaude.textContent = s.anthropic_ok ? "Claude ready" : "No API key";
    document.getElementById("badge-claude").classList.toggle("badge-ok", s.anthropic_ok);
    document.getElementById("badge-claude").classList.toggle("badge-err", !s.anthropic_ok);

    if (!s.anthropic_ok) {
      logLine("ANTHROPIC_API_KEY is not set in scripts/.env", "error");
      logLine("Add it and restart the server.", "muted");
    }

    syncRunBtn(s.anthropic_ok);
    return s;
  } catch {
    dotAppian.className = "dot err";
    textAppian.textContent = "Server unreachable";
    return null;
  }
}

// ── Load app list ─────────────────────────────────────────────────────────────
async function loadApps() {
  appSelect.innerHTML = '<option value="">— loading —</option>';
  appError.classList.add("hidden");

  try {
    const r = await fetch("/api/apps");
    if (!r.ok) {
      const d = await r.json();
      throw new Error(d.detail || r.statusText);
    }
    const { apps } = await r.json();
    appSelect.innerHTML = '<option value="">— no selection (work from scratch) —</option>';
    (apps || []).forEach(a => {
      const o = document.createElement("option");
      o.value       = a.uuid || a.id || "";
      o.textContent = a.name || a.uuid || "(unnamed)";
      appSelect.appendChild(o);
    });
  } catch (e) {
    appError.textContent = `Could not load apps: ${e.message}`;
    appError.classList.remove("hidden");
    appSelect.innerHTML = '<option value="">— unavailable —</option>';
  }
}

function syncRunBtn(anthropicOk) {
  btnRun.disabled = !requirement.value.trim() || !anthropicOk;
}
requirement.addEventListener("input", () => syncRunBtn(!btnRun.disabled || !!requirement.value.trim()));

// ── Stage management ──────────────────────────────────────────────────────────
const STAGE_ORDER = ["designer", "developer", "designer_verify", "tester"];

const STAGE_ICONS = {
  start:   '<span class="spin-icon">⟳</span>',
  running: '<span class="spin-icon">⟳</span>',
  done:    '<span class="check-icon">✓</span>',
  error:   '<span class="error-icon">✗</span>',
};

function resetStages() {
  stagesEl.classList.add("hidden");
  STAGE_ORDER.forEach(id => {
    const icon = document.getElementById(`icon-${id}`);
    const body = document.getElementById(`body-${id}`);
    if (icon) icon.innerHTML = "";
    if (body) body.innerHTML = '<div class="stage-thinking">Waiting…</div>';
    const card = document.getElementById(`stage-${id}`);
    if (card) card.className = "stage-card";
  });
}

function handleStageEvent(ev) {
  const { stage, status, message, data } = ev;

  stagesEl.classList.remove("hidden");

  const card = document.getElementById(`stage-${stage}`);
  const icon = document.getElementById(`icon-${stage}`);
  const body = document.getElementById(`body-${stage}`);
  if (!card) return;

  // Update card class
  card.className = "stage-card stage-" + status;

  // Update icon
  if (icon) icon.innerHTML = STAGE_ICONS[status] || "";

  // Update body
  if (body && message) {
    if (status === "start" || status === "running") {
      body.innerHTML = `<div class="stage-thinking"><span class="dot-pulse"></span> ${escHtml(message)}</div>`;
    } else if (status === "done") {
      body.innerHTML = `<div class="stage-done-msg">${escHtml(message)}</div>`
        + renderStageData(stage, data);
    } else if (status === "error") {
      body.innerHTML = `<div class="stage-error-msg">${escHtml(message)}</div>`;
    }
  }
}

function renderStageData(stage, data) {
  if (!data || Object.keys(data).length === 0) return "";

  if (stage === "designer") {
    const newObjs = (data.new_objects || []).map(o => o.name).join(", ");
    const modObjs = (data.modified_objects || []).map(o => o.name).join(", ");
    let html = `<div class="stage-summary">`;
    if (data.summary) html += `<p>${escHtml(data.summary)}</p>`;
    if (newObjs)  html += `<div class="obj-chips"><span class="chip chip-new">New:</span> ${escHtml(newObjs)}</div>`;
    if (modObjs)  html += `<div class="obj-chips"><span class="chip chip-mod">Modified:</span> ${escHtml(modObjs)}</div>`;
    html += `</div>`;
    return html;
  }

  if (stage === "developer") {
    const newObjs = (data.new_objects || []).map(o => o.name).join(", ");
    const modObjs = (data.modified_objects || []).map(o => o.name).join(", ");
    const reused  = (data.reused_components || []).join(", ");
    let html = `<div class="stage-summary">`;
    if (data.implementation_summary) html += `<p>${escHtml(data.implementation_summary)}</p>`;
    if (newObjs) html += `<div class="obj-chips"><span class="chip chip-new">Built:</span> ${escHtml(newObjs)}</div>`;
    if (modObjs) html += `<div class="obj-chips"><span class="chip chip-mod">Modified:</span> ${escHtml(modObjs)}</div>`;
    if (reused)  html += `<div class="obj-chips"><span class="chip chip-reuse">Reused:</span> ${escHtml(reused)}</div>`;
    html += `</div>`;
    return html;
  }

  if (stage === "designer_verify") {
    const score    = data.completeness_score ?? "—";
    const approved = data.approved;
    const issues   = data.issues || [];
    let html = `<div class="stage-summary">`;
    html += `<div class="verify-score">
      Completeness: <strong>${score}/100</strong>
      <span class="verify-badge ${approved ? 'v-ok' : 'v-fail'}">${approved ? "Approved" : "Needs revision"}</span>
    </div>`;
    if (issues.length) {
      html += `<div class="issues-list">`;
      issues.forEach(iss => {
        html += `<div class="issue-item issue-${iss.severity}">
          <span class="issue-sev">${iss.severity}</span>
          <span class="issue-obj">${escHtml(iss.object || "")}</span>
          <span class="issue-desc">${escHtml(iss.issue || "")}</span>
        </div>`;
      });
      html += `</div>`;
    }
    html += `</div>`;
    return html;
  }

  if (stage === "tester") {
    const sum = data.summary || {};
    let html = `<div class="stage-summary">`;
    html += `<div class="test-pills">
      <span class="tp pass">${sum.passed ?? 0} passed</span>
      <span class="tp fail">${sum.failed ?? 0} failed</span>
      <span class="tp warn">${sum.warnings ?? 0} warnings</span>
    </div>`;
    if (data.deployment_recommendation)
      html += `<p class="deploy-rec">${escHtml(data.deployment_recommendation)}</p>`;
    html += `</div>`;
    return html;
  }

  return "";
}

// ── SSE streaming ─────────────────────────────────────────────────────────────
function streamJob(jobId, onDone) {
  const es = new EventSource(`/api/jobs/${jobId}/stream`);

  es.onmessage = e => {
    const data = JSON.parse(e.data);

    if (data.type === "log") {
      logLine(data.msg, classifyLine(data.msg));
    } else if (data.type === "workflow_event") {
      handleStageEvent(data);
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

// ── Run workflow ──────────────────────────────────────────────────────────────
btnRun.addEventListener("click", async () => {
  const req = requirement.value.trim();
  if (!req) return;

  clearLog();
  resetStages();
  resetObjects();
  stagesEl.classList.remove("hidden");

  btnRun.disabled  = true;
  btnRun.innerHTML = '<span class="spinning">⟳</span> Agents working…';
  setBadge("running", "● Running");

  try {
    const r = await fetch("/api/workflow", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        requirement: req,
        app_uuid:    appSelect.value || "",
      }),
    });
    if (!r.ok) throw new Error((await r.json()).detail);
    const { job_id } = await r.json();

    streamJob(job_id, (result, error) => {
      btnRun.disabled  = false;
      btnRun.innerHTML =
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
        + '<circle cx="12" cy="12" r="3"/>'
        + '<path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>'
        + '</svg> Run AI Workflow';

      if (error) {
        setBadge("failed", "✗ Failed");
        logLine(`Workflow error: ${error}`, "error");
      } else if (result) {
        setBadge("done", "✓ Done");
        _workflowResult = result;
        renderObjects(result);
      } else {
        setBadge("failed", "✗ No output");
      }
    });
  } catch (e) {
    setBadge("failed", "✗ Error");
    logLine(`Request failed: ${e.message}`, "error");
    btnRun.disabled  = false;
    btnRun.innerHTML =
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
      + '<circle cx="12" cy="12" r="3"/>'
      + '<path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>'
      + '</svg> Run AI Workflow';
  }
});

// ── Render objects ────────────────────────────────────────────────────────────
function resetObjects() {
  _workflowResult = null;
  objectsEmpty.classList.remove("hidden");
  objectsPanel.classList.add("hidden");
  newSection.classList.add("hidden");
  modSection.classList.add("hidden");
  newList.innerHTML = "";
  modList.innerHTML = "";
  testSummaryBar.classList.add("hidden");
  tabObjects.disabled = true;
  objectsCount.classList.add("hidden");
  btnDeploy.disabled = true;
}

function renderObjects(result) {
  const newObjs = result.new_objects  || [];
  const modObjs = result.modified_objects || [];
  const total   = newObjs.length + modObjs.length;

  objectsEmpty.classList.add("hidden");
  objectsPanel.classList.remove("hidden");

  // New objects
  if (newObjs.length) {
    newSection.classList.remove("hidden");
    newCount.textContent = newObjs.length;
    newList.innerHTML = newObjs.map(obj => objectCard(obj, "new")).join("");
  }

  // Modified objects
  if (modObjs.length) {
    modSection.classList.remove("hidden");
    modCount.textContent = modObjs.length;
    modList.innerHTML = modObjs.map(obj => objectCard(obj, "modified")).join("");
  }

  // Test summary bar
  const ts = result.test_summary || {};
  if (ts.total_tests > 0) {
    testSummaryBar.classList.remove("hidden");
    testPassed.textContent  = `${ts.passed ?? 0} passed`;
    testFailed.textContent  = `${ts.failed ?? 0} failed`;
    testWarn.textContent    = `${ts.warnings ?? 0} warnings`;
    const ready = result.ready_for_deployment;
    deployReadiness.textContent  = ready ? "Ready for deployment" : "Review before deploying";
    deployReadiness.className    = "deploy-badge " + (ready ? "deploy-ok" : "deploy-warn");
  }

  // Deploy button
  btnDeploy.disabled = !_appianReady;
  if (!_appianReady) {
    noAppianNote.classList.remove("hidden");
  }

  // Enable Objects tab
  tabObjects.disabled = false;
  objectsCount.textContent = total;
  objectsCount.classList.remove("hidden");

  // Switch to Objects tab
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  tabObjects.classList.add("active");
  document.getElementById("tab-panel-objects").classList.add("active");

  // Wire up expand/collapse
  document.querySelectorAll(".obj-card-toggle").forEach(btn => {
    btn.addEventListener("click", function () {
      const card = this.closest(".obj-card");
      card.classList.toggle("expanded");
      this.textContent = card.classList.contains("expanded") ? "Hide code" : "Show code";
    });
  });
}

function objectCard(obj, kind) {
  const type    = escHtml(obj.type || "Object");
  const name    = escHtml(obj.name || "(unnamed)");
  const desc    = escHtml(obj.description || obj.changes_made || "");
  const content = escHtml(obj.content || obj.modified_content || "");
  const reuses  = (obj.reuses || []).join(", ");

  return `
<div class="obj-card">
  <div class="obj-card-header">
    <span class="type-badge type-${slugify(obj.type)}">${type}</span>
    <span class="obj-name">${name}</span>
    <button class="obj-card-toggle btn-ghost">Show code</button>
  </div>
  ${desc ? `<div class="obj-desc">${desc}</div>` : ""}
  ${reuses ? `<div class="obj-reuse">Reuses: <em>${escHtml(reuses)}</em></div>` : ""}
  <div class="obj-code-wrap">
    <pre class="obj-code">${content}</pre>
  </div>
</div>`;
}

// ── Deploy objects ────────────────────────────────────────────────────────────
btnDeploy.addEventListener("click", async () => {
  if (!_workflowResult) return;
  const allObjs = [
    ...(_workflowResult.new_objects || []),
    ...(_workflowResult.modified_objects || []),
  ];
  if (!allObjs.length) return;

  btnDeploy.disabled  = true;
  btnDeploy.innerHTML = '<span class="spinning">⟳</span> Deploying…';
  setBadge("running", "● Deploying");

  // Switch to workflow tab to show log
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.querySelector('[data-tab="workflow"]').classList.add("active");
  document.getElementById("tab-panel-workflow").classList.add("active");

  try {
    const r = await fetch("/api/deploy-objects", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        objects:     allObjs,
        deploy_name: deployName.value.trim() || "AI-generated deployment",
      }),
    });
    if (!r.ok) throw new Error((await r.json()).detail);
    const { job_id } = await r.json();

    streamJob(job_id, (result, error) => {
      btnDeploy.disabled  = false;
      btnDeploy.innerHTML =
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
        + '<path d="M22 2L11 13"/><path d="M22 2L15 22 11 13 2 9l20-7z"/>'
        + '</svg> Deploy Objects';

      if (error) {
        setBadge("failed", "✗ Deploy failed");
        logLine(`Deploy error: ${error}`, "error");
      } else if (result?.ok) {
        setBadge("done", "✓ Deployed");
        logLine(`Deployment UUID: ${result.uuid}`, "info");
      } else {
        setBadge("failed", `✗ ${result?.status || "Failed"}`);
        btnDeploy.disabled = false;
      }
    });
  } catch (e) {
    setBadge("failed", "✗ Error");
    logLine(`Request failed: ${e.message}`, "error");
    btnDeploy.disabled  = false;
    btnDeploy.innerHTML =
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
      + '<path d="M22 2L11 13"/><path d="M22 2L15 22 11 13 2 9l20-7z"/>'
      + '</svg> Deploy Objects';
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function slugify(str) {
  return String(str ?? "").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  const s = await checkStatus();
  if (s?.appian_ok) {
    await loadApps();
  } else {
    appSelect.innerHTML = '<option value="">— no Appian connection —</option>';
    if (s?.anthropic_ok) {
      logLine("Appian not configured — workflow will run without existing object context.", "warn");
      logLine("You can still design and generate objects from scratch.", "muted");
    }
  }
})();
