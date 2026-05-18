const RUNBOOK_TOKEN_KEY = "runbookHermesApiToken";
const RUNBOOK_TOKEN_HEADER = "x-runbook-token";

function tokenFromUrl() {
  const params = new URLSearchParams(window.location.search || "");
  const token = params.get("runbook_token") || params.get("token") || "";
  if (token) {
    localStorage.setItem(RUNBOOK_TOKEN_KEY, token);
    params.delete("runbook_token");
    params.delete("token");
    const qs = params.toString();
    history.replaceState({}, document.title, window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash);
  }
  return token;
}

tokenFromUrl();

function getRunbookToken() {
  return localStorage.getItem(RUNBOOK_TOKEN_KEY) || sessionStorage.getItem(RUNBOOK_TOKEN_KEY) || "";
}

function setRunbookToken(token) {
  const value = String(token || "").trim();
  if (value) localStorage.setItem(RUNBOOK_TOKEN_KEY, value);
  else localStorage.removeItem(RUNBOOK_TOKEN_KEY);
}

function clearRunbookToken() {
  localStorage.removeItem(RUNBOOK_TOKEN_KEY);
  sessionStorage.removeItem(RUNBOOK_TOKEN_KEY);
}

function saveTokenFromNav() {
  const input = document.getElementById("runbook-token-input");
  setRunbookToken(input ? input.value : "");
  toast("API token saved locally in this browser");
  loadRuntimeChip().catch(() => {});
}

function clearTokenFromNav() {
  clearRunbookToken();
  const input = document.getElementById("runbook-token-input");
  if (input) input.value = "";
  toast("API token cleared");
  loadRuntimeChip().catch(() => {});
}


async function downloadTextWithToken(path, filename = "runbook.md") {
  const token = getRunbookToken();
  const headers = {};
  if (token) {
    headers[RUNBOOK_TOKEN_HEADER] = token;
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(path, { headers });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Download failed (${res.status}). Add a RunbookHermes token in Settings or the sidebar. ${detail}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function downloadSkill(skillId) {
  const safe = String(skillId || "runbook-skill").replace(/[^a-zA-Z0-9_.-]+/g, "_");
  await downloadTextWithToken(`/skills/${encodeURIComponent(skillId)}/download`, `${safe}.md`);
}

async function api(path, options = {}) {
  const token = getRunbookToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token && !headers[RUNBOOK_TOKEN_HEADER]) headers[RUNBOOK_TOKEN_HEADER] = token;
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const detail = await res.text();
    if ([401, 403, 503].includes(res.status)) {
      throw new Error(`API authentication failed (${res.status}). Add a RunbookHermes token in Settings or the sidebar. ${detail}`);
    }
    throw new Error(detail);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : {};
}

function fmtTime(ts) {
  if (!ts) return "-";
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return String(ts);
  return d.toLocaleString();
}

function short(id) {
  return id ? String(id).slice(0, 10) : "-";
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function pct(v, digits = 1) {
  const n = Number(v || 0) * 100;
  return `${n.toFixed(digits)}%`;
}

function num(v, digits = 2) {
  const n = Number(v || 0);
  return Number.isFinite(n) ? n.toFixed(digits) : "0";
}

function badge(value, extra = "") {
  const v = String(value || "-");
  const cls = v.toLowerCase().replace(/[^a-z0-9_]+/g, "_");
  return `<span class="badge ${cls} ${extra}">${esc(v)}</span>`;
}

function riskBadge(v) { return badge(v || "unknown"); }

function jsonBlock(obj) {
  return `<pre>${esc(JSON.stringify(obj || {}, null, 2))}</pre>`;
}

function nav(active) {
  const items = [
    ["index", "/web/index.html", "Overview"],
    ["monitoring", "/web/monitoring.html", "Monitoring"],
    ["incidents", "/web/incidents.html", "Incidents"],
    ["approvals", "/web/approvals.html", "Approvals"],
    ["digests", "/web/digests.html", "Digests"],
    ["memory", "/web/memory.html", "Memory"],
    ["rag", "/web/rag.html", "RAG 知识库"],
    ["eval", "/web/eval.html", "Benchmark/Eval"],
    ["training", "/web/training.html", "Training/RL"],
    ["multimodal", "/web/multimodal.html", "Multimodal"],
    ["settings", "/web/settings.html", "Settings"],
  ];
  return `<aside class="sidebar">
    <div class="brand"><div class="logo">RH</div><h1>RunbookHermes</h1></div>
    <nav class="nav">
      ${items.map(([key, href, label]) => `<a class="${active === key ? "active" : ""}" href="${href}">${label}</a>`).join("")}
    </nav>
    <div class="side-card">
      <div class="muted">Safety rule</div>
      <b>Destructive action = approval + checkpoint + dry-run first.</b>
    </div>
    <div class="side-card auth-card">
      <div class="muted">API token</div>
      <input id="runbook-token-input" type="password" placeholder="x-runbook-token" value="${esc(getRunbookToken())}" autocomplete="off" />
      <div class="mini-actions"><button class="secondary" onclick="saveTokenFromNav()">Save</button><button class="ghost" onclick="clearTokenFromNav()">Clear</button></div>
      <p class="muted tiny">Stored only in this browser. Also supports ?runbook_token=...</p>
    </div>
    <div class="side-card" id="runtime-chip"><span class="muted">Loading runtime status...</span></div>
  </aside>`;
}

function shell(active, body) {
  document.body.innerHTML = `<div class="shell">${nav(active)}<main class="content">${body}</main></div><div id="toast-root"></div>`;
  if (active === "memory") {
    const title = document.querySelector(".page-title");
    if (title && /越用越懂系统的 RunbookHermes|Memory控制台/.test(title.textContent || "")) {
      title.textContent = "Memory控制台";
    }
  }
  loadRuntimeChip().catch(() => {});
}

function toast(msg) {
  const root = document.getElementById("toast-root") || document.body;
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = esc(msg);
  root.appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

async function loadRuntimeChip() {
  const el = document.getElementById("runtime-chip");
  if (!el) return;
  const s = await api("/runtime/status");
  el.innerHTML = `
    <div class="muted">Runtime</div>
    <div>${badge(s.observability?.obs_backend || "mock")} ${badge(s.observability?.trace_provider_kind || "trace")}</div>
    <div style="margin-top:8px">${s.model?.enabled ? badge("model on","done") : badge("model off","pending")}</div>
    <div style="margin-top:8px">${s.execution?.controlled_execution_enabled ? badge("controlled exec on","done") : badge("controlled exec off","pending")}</div>
    <div style="margin-top:8px">${s.memory?.enabled ? badge("memory on","done") : badge("memory off","pending")}</div>
  `;
}

function sourceLabel(source) {
  const s = String(source || "unknown").toLowerCase();
  if (s.includes("prom")) return "📈 metrics";
  if (s.includes("loki") || s.includes("log")) return "📜 logs";
  if (s.includes("trace") || s.includes("jaeger")) return "🔎 trace";
  if (s.includes("deploy")) return "🚀 deploy";
  return "🧩 evidence";
}

function renderEvidence(ev) {
  return `<div class="evidence-card">
    <div class="split"><span class="source">${sourceLabel(ev.source)}</span><span>${badge(ev.severity || ev.confidence || "evidence")}</span></div>
    <h3>${esc(ev.evidence_id || "evidence")}</h3>
    <p>${esc(ev.summary || "")}</p>
    <p class="dim">${esc(ev.raw_ref || "")}</p>
  </div>`;
}

function renderEvent(event) {
  return `<div class="timeline-item">
    <div class="split"><b>${esc(event.event_type || "-")}</b><span class="dim">${fmtTime(event.ts)}</span></div>
    <div class="dim">${esc(JSON.stringify(event.payload || {}).slice(0, 260))}</div>
  </div>`;
}

function getParam(name) {
  return new URLSearchParams(location.search).get(name);
}

function linePath(values, width = 280, height = 70) {
  const nums = values.map(v => Number(v || 0));
  const max = Math.max(...nums, 0.001);
  const step = width / Math.max(nums.length - 1, 1);
  return nums.map((v, i) => {
    const x = i * step;
    const y = height - (v / max) * (height - 8) - 4;
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function sparkline(rows, key, label, format = "num") {
  const values = (rows || []).map(r => r[key] || 0);
  const latest = values.length ? values[values.length - 1] : 0;
  const display = format === "pct" ? pct(latest) : format === "ms" ? `${num(latest * 1000, 0)}ms` : num(latest);
  return `<div class="spark-card">
    <div class="split"><span class="muted">${esc(label)}</span><b>${display}</b></div>
    <svg viewBox="0 0 280 76" preserveAspectRatio="none" class="spark"><path d="${linePath(values)}"></path></svg>
  </div>`;
}

function miniBars(metrics) {
  const rows = [
    ["503", metrics.http_503_rate || 0, "danger"],
    ["504", metrics.http_504_rate || 0, "warning"],
    ["429", metrics.http_429_rate || 0, "info"],
  ];
  const max = Math.max(...rows.map(r => r[1]), 0.01);
  return `<div class="bar-list">${rows.map(([label, value, cls]) => `<div class="bar-row"><span>${label}</span><div class="bar-track"><i class="${cls}" style="width:${Math.max(4, (value / max) * 100)}%"></i></div><b>${pct(value)}</b></div>`).join("")}</div>`;
}

function healthClass(state) {
  return String(state || "unknown").toLowerCase();
}
