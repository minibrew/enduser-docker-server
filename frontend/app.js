"use strict";

// ── Constants ────────────────────────────────────────────────────────────────

const WS_BASE = window.location.hostname === "localhost"
  ? "ws://localhost:8000"
  : `ws://${window.location.host}`;

const JWT_TOKEN_KEY = "minibrew_jwt_token";
const REFRESH_TOKEN_KEY = "minibrew_refresh_token";

const PROCESS_STATE_MAP = {
  0: "IDLE_STATE", 5: "MANUAL_CONTROL_STATE", 6: "PREPARE_RINSE_STATE",
  7: "CHECK_KEG_STATE", 8: "CHECK_WATER_STATE", 10: "PUMP_PRIMING_STATE",
  11: "CHECK_FLOW_STATE", 12: "HEATUP_RINSE_STATE", 13: "CLEAN_BALL_VALVE_STATE",
  14: "RINSE_BOILING_PATH_STATE", 15: "RINSE_MASHING_PATH_STATE",
  16: "RINSE_DONE_STATE", 17: "FILL_MACHINE_STATE", 18: "RINSE_COOL_STATE",
  24: "MASH_IN_STATE", 30: "MASHING_HEATUP_STATE", 31: "MASHING_MAINTAIN_STATE",
  39: "SPARGING_STATE", 40: "LAUTERING_STATE", 43: "REPLACE_MASH_STATE",
  50: "BOILING_HEATUP_STATE", 51: "BOILING_MAINTAIN_STATE",
  52: "SECONDARY_LAUTERING_STATE", 59: "CONNECT_WATER_STATE",
  60: "COOL_WORT_STATE", 70: "BREWING_DONE_STATE", 71: "BREWING_FAILED_STATE",
  74: "PITCH_COOLING_STATE", 75: "PREPARE_FERMENTATION_STATE",
  76: "PLACE_AIRLOCK_STATE", 77: "REMOVE_AIRLOCK_STATE",
  78: "PLACE_TRUB_CONTAINER_STATE", 80: "FERMENTATION_TEMP_CONTROL_STATE",
  81: "REMOVE_TRUB_STATE", 82: "FERMENTATION_ADD_INGREDIENT_STATE",
  83: "FERMENTATION_REMOVE_INGREDIENT_STATE", 84: "FERMENTATION_FAILED_STATE",
  88: "PREPARE_SERVING_STATE", 90: "COOL_BEFORE_SERVING_STATE",
  91: "MOUNT_TAP_STATE", 92: "SERVING_TEMP_CONTROL_STATE",
  93: "SERVING_FAILED_STATE", 101: "PREPARE_CIP_STATE", 103: "BACKFLUSH_STATE",
  108: "CIP_DONE_STATE", 109: "CIP_FAILED_STATE",
  111: "CIRCULATE_BOILING_PATH_STATE", 112: "CIRCULATE_MASHING_PATH_STATE",
  113: "RINSE_COUNTERFLOW_BOIL_STATE", 114: "RINSE_COUNTERFLOW_MASHTUN_STATE",
};

const USER_ACTION_MAP = {
  0: "None", 2: "Prepare cleaning", 3: "Add cleaning agent",
  4: "Fill water", 5: "Ready to clean", 12: "Needs cleaning",
  13: "Needs acid cleaning", 21: "Start brewing", 22: "Add ingredients",
  23: "Mash in", 24: "Heat to mash", 25: "Mash done",
  26: "Prepare fermentation", 27: "Cool to fermentation", 28: "Add yeast",
  30: "Fermentation complete", 31: "Transfer to serving",
  32: "Start cleaning", 33: "Rinse", 34: "Acid clean", 35: "Sanitize",
  36: "Finished cleaning", 37: "CIP Finished",
};

const PROCESS_TYPE_MAP = { 0: "Brewing", 1: "Fermentation", 2: "Cleaning" };
const FAILURE_STATES = [71, 84, 93, 109];
const SESSION_STATUS_MAP = { 1: "Active", 2: "In Progress", 4: "Done", 6: "Failed" };

const CMD_DEFINITIONS = [
  { cmd: "END_SESSION",       type: null,  allowedUA: [], desc: "Terminate and delete the session from the device" },
  { cmd: "NEXT_STEP",         type: 3,    allowedUA: "*", desc: "Advance to the next brewing step" },
  { cmd: "BYPASS_USER_ACTION", type: 3,  allowedUA: "*", desc: "Bypass the pending user action prompt" },
  { cmd: "CHANGE_TEMPERATURE", type: 6,  allowedUA: [26,27,28,30,31,32], desc: "Set target fermentation/serving temperature" },
  { cmd: "GO_TO_MASH",        type: 3,   allowedUA: [21,22,23,24], desc: "Jump directly to the mash phase" },
  { cmd: "GO_TO_BOIL",        type: 3,   allowedUA: [23,24,25], desc: "Jump directly to the boil phase" },
  { cmd: "FINISH_BREW_SUCCESS", type: 3,  allowedUA: [30], desc: "Mark the brew as completed successfully" },
  { cmd: "FINISH_BREW_FAILURE", type: 3,   allowedUA: [71,84], desc: "Mark the brew as failed" },
  { cmd: "CLEAN_AFTER_BREW",  type: 3,   allowedUA: [30,31], desc: "Begin post-brew cleaning cycle" },
  { cmd: "BYPASS_CLEAN",      type: 3,   allowedUA: [32,33,34,35,36,37], desc: "Skip the cleaning cycle" },
];

// ── State ───────────────────────────────────────────────────────────────────

let ws = null;
let sessionsData = [];
let kegsData = [];
let recipesData = [];
let selectedRecipeId = null;
let currentSessionId = null;
let currentKegUuid = null;
let activeSource = "overview";
let autoRefreshInterval = null;
let autoRefreshSeconds = 2;
let suppressWsLogs = true;
let activeSessionFromDevice = null;
let allDevices = [];   // [{uuid, custom_name, _bucket, ...}, ...]
let selectedBucket = null;
let selectedSessionDetail = null;
let currentUser = null;   // {id, username} from JWT

// ── Utilities ───────────────────────────────────────────────────────────────

function sessionKey(s) { return s?.id ?? s?.session_id ?? null; }

function fmt(v) { return v == null || v === "" ? null : v; }

function stateLabel(v) {
  if (v == null) return { text: "—", cls: "val-null" };
  const known = PROCESS_STATE_MAP[v];
  if (known) return { text: `${v} (${known})`, cls: "val-code" };
  return { text: `${v} (NULL)`, cls: "val-null" };
}

function uaLabel(v) {
  if (v == null) return { text: "—", cls: "" };
  const known = USER_ACTION_MAP[v];
  if (known) return { text: `${v} (${known})`, cls: "val-code" };
  return { text: `${v} (NULL)`, cls: "val-null" };
}

function boolLabel(v) { return v ? "Yes" : "No"; }

function phaseOf(state) {
  const m = {
    24:"BREWING",30:"BREWING",31:"BREWING",40:"BREWING",
    50:"BREWING",51:"BREWING",52:"BREWING",60:"BREWING",
    70:"BREWING",71:"BREWING",74:"BREWING",
    75:"FERMENTATION",80:"FERMENTATION",84:"FERMENTATION",
    88:"SERVING",90:"SERVING",91:"SERVING",92:"SERVING",93:"SERVING",
    101:"CLEANING",103:"CLEANING",108:"CLEANING",109:"CLEANING",
    111:"CLEANING",112:"CLEANING",113:"CLEANING",114:"CLEANING",
  };
  return m[state] || null;
}

function prettyJson(obj) {
  return JSON.stringify(obj, null, 2);
}

// ── JWT helpers ─────────────────────────────────────────────────────────────

function getJwtToken() { return localStorage.getItem(JWT_TOKEN_KEY); }
function setJwtToken(t) { localStorage.setItem(JWT_TOKEN_KEY, t); }
function clearJwtToken() {
  localStorage.removeItem(JWT_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  currentUser = null;
}

function showAuthGate() {
  document.getElementById("auth-gate").style.display = "flex";
  document.getElementById("token-gate").style.display = "none";
  document.getElementById("navbar-username").style.display = "none";
  document.getElementById("navbar-logout-btn").style.display = "none";
}

function showTokenGate() {
  document.getElementById("auth-gate").style.display = "none";
  document.getElementById("token-gate").style.display = "flex";
  document.getElementById("gate-token-input").value = "";
}

function showDashboard(user) {
  currentUser = user;
  document.getElementById("auth-gate").style.display = "none";
  document.getElementById("token-gate").style.display = "none";
  const usernameEl = document.getElementById("navbar-username");
  const logoutBtn = document.getElementById("navbar-logout-btn");
  if (usernameEl) { usernameEl.textContent = user.username; usernameEl.style.display = ""; }
  if (logoutBtn) logoutBtn.style.display = "";
  checkTokenAndGate();
}

function handleAuthError() {
  clearJwtToken();
  showAuthGate();
}

// ── Auth-fetch wrapper ────────────────────────────────────────────────────────

async function fetchWithAuth(url, options = {}) {
  const token = getJwtToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(url, { ...options, headers });
  if (resp.status === 401) {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (refreshToken) {
      const refreshResp = await fetch("/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (refreshResp.ok) {
        const data = await refreshResp.json();
        setJwtToken(data.access_token);
        localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
        headers["Authorization"] = `Bearer ${data.access_token}`;
        const retryResp = await fetch(url, { ...options, headers });
        if (retryResp.status === 401) { handleAuthError(); return null; }
        return retryResp;
      }
    }
    handleAuthError();
    return null;
  }
  return resp;
}

// ── Logging ─────────────────────────────────────────────────────────────────

function log(msg, type = "info") {
  if (suppressWsLogs && (type === "info" || type === "warn")) {
    if (msg.includes("WebSocket connected") || msg.includes("WebSocket disconnected")) return;
  }
  const el = document.getElementById("log-output");
  if (!el) return;
  const entry = document.createElement("div");
  entry.className = `log-entry log-${type}`;
  const time = new Date().toLocaleTimeString();
  entry.textContent = `[${time}] ${msg}`;
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
}
const logError = (m) => log(m, "error");
const logSuccess = (m) => log(m, "success");
const logWarn = (m) => log(m, "warn");

// ── WebSocket ────────────────────────────────────────────────────────────────

function connect() {
  ws = new WebSocket(`${WS_BASE}/ws`);
  ws.onopen = () => {
    document.getElementById("connection-indicator").textContent = "🟢";
    log("WebSocket connected");
  };
  ws.onclose = () => {
    document.getElementById("connection-indicator").textContent = "⚫";
    logWarn("WebSocket disconnected — reconnecting in 3s");
    setTimeout(connect, 3000);
  };
  ws.onerror = () => {
    document.getElementById("connection-indicator").textContent = "🔴";
    logError("WebSocket error");
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "initial_state") handleInitialState(msg.payload);
    else if (msg.type === "device_update") handleDeviceUpdate(msg.payload);
    else if (msg.type === "session_update") handleSessionUpdate(msg.payload);
    else if (msg.type === "bucket_changed") handleBucketChanged(msg.payload);
    else if (msg.type === "system_event") log(JSON.stringify(msg), "warn");
  };
}

function wsSend(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

// ── WebSocket handlers ──────────────────────────────────────────────────────

function handleInitialState(payload) {
  allDevices = payload.devices || [];
  selectedBucket = payload.selected_bucket || null;
  sessionsData = payload.sessions || [];
  kegsData = payload.kegs || [];
  activeSessionFromDevice = payload.device?.active_session ?? null;

  populateDeviceDropdown();
  if (selectedBucket) selectBucketInDropdown(selectedBucket);
  renderSessions(sessionsData);
  renderKegs(kegsData);
  updateDeviceUI(payload.device);
  refreshCommandsTable();
  buildCodeTables();
}

function handleDeviceUpdate(payload) {
  allDevices = payload.devices || [];
  selectedBucket = payload.selected_bucket || selectedBucket;
  sessionsData = payload.sessions || sessionsData;
  kegsData = payload.kegs || kegsData;

  populateDeviceDropdown();
  if (selectedBucket) selectBucketInDropdown(selectedBucket);
  renderSessions(sessionsData);
  renderKegs(kegsData);

  const selectedDevice = payload.devices?.find(d =>
    `${d._bucket || ""}` === `${selectedBucket || ""}`) || payload.devices?.[0];
  if (selectedDevice) updateDeviceUI({ ...selectedDevice, _raw: selectedDevice });
}

function handleBucketChanged(payload) {
  selectedBucket = payload.bucket;
  sessionsData = payload.sessions || sessionsData;
  selectBucketInDropdown(payload.bucket);
  const dev = allDevices.find(d => d._bucket === payload.bucket);
  if (dev) updateDeviceUI({ ...dev, _raw: dev });
  renderSessions(sessionsData);
}

function handleSessionUpdate(payload) {
  if (payload.sessions) {
    sessionsData = payload.sessions;
    renderSessions(sessionsData);
  }
}

// ── Device dropdown ─────────────────────────────────────────────────────────

function populateDeviceDropdown() {
  const sel = document.getElementById("device-select");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">— select device —</option>';
  for (const dev of allDevices) {
    const uuid = dev.uuid || dev.serial_number || dev._bucket || "?";
    const name = dev.title || dev.custom_name || uuid;
    const bucket = dev._bucket || "";
    const isActive = bucket === selectedBucket;
    const opt = document.createElement("option");
    opt.value = bucket;
    opt.textContent = `${name} (${uuid})${isActive ? " ★" : ""}`;
    opt.dataset.uuid = uuid;
    sel.appendChild(opt);
  }
  if (current) sel.value = current;
}

function selectBucketInDropdown(bucket) {
  const sel = document.getElementById("device-select");
  if (sel) sel.value = bucket;
}

function onDeviceSelectChange(e) {
  const bucket = e.target.value;
  if (!bucket) return;
  wsSend({ type: "select_bucket", bucket });
}

// ── Tab navigation ──────────────────────────────────────────────────────────

function initTabs() {
  document.querySelectorAll(".navbar__tab").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".navbar__tab").forEach(b => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.id === `tab-${tab}`));
    });
  });
}

// ── Device info ─────────────────────────────────────────────────────────────

function updateDeviceUI(device) {
  if (!device) return;
  const d = device._raw || device;
  const ps = d.process_state ?? null;
  const ua = d.user_action ?? null;
  const stateInfo = stateLabel(ps);
  const uaInfo = uaLabel(ua);
  const phase = phaseOf(ps);
  const isFail = FAILURE_STATES.includes(ps);

  document.getElementById("info-uuid").textContent = d.uuid || d.serial_number || "—";
  document.getElementById("info-custom-name").textContent = d.title || d.custom_name || "—";
  document.getElementById("info-stage").textContent = d.stage || "—";
  const psEl = document.getElementById("info-process-state");
  if (psEl) { psEl.textContent = stateInfo.text; psEl.className = `device-field__value ${stateInfo.cls}`; }
  const uaEl = document.getElementById("info-user-action");
  if (uaEl) { uaEl.textContent = uaInfo.text; uaEl.className = `device-field__value ${uaInfo.cls}`; }
  document.getElementById("info-current-temp").textContent = d.current_temp != null ? `${d.current_temp}°C` : "—";
  document.getElementById("info-target-temp").textContent = d.target_temp != null ? `${d.target_temp}°C` : "—";
  document.getElementById("info-gravity").textContent = d.gravity || "—";
  document.getElementById("info-beer-name").textContent = d.beer_name || "—";
  document.getElementById("info-active-session").textContent = d.session_id || d.active_session || "—";
  document.getElementById("info-online").textContent = d.online != null ? boolLabel(d.online) : "—";
  document.getElementById("info-software-version").textContent = d.software_version || "—";

  const headerState = document.getElementById("process-state");
  const headerPhase = document.getElementById("phase-label");
  if (headerState) headerState.textContent = isFail ? `FAIL: ${stateInfo.text}` : stateInfo.text;
  if (headerPhase) headerPhase.textContent = phase ? `[${phase}]` : "—";

  const rawEl = document.getElementById("info-raw-json");
  if (rawEl) rawEl.textContent = prettyJson(d);

  const deviceSectionTitle = document.getElementById("device-section-title");
  if (deviceSectionTitle) {
    const name = d.title || d.custom_name || "Device Info";
    deviceSectionTitle.textContent = name;
  }
}

// ── Sessions ────────────────────────────────────────────────────────────────

function renderSessions(sessions) {
  const sel = document.getElementById("session-select");
  if (!sel) return;
  if (!sessions || sessions.length === 0) {
    sel.innerHTML = '<option value="">— no sessions —</option>';
    return;
  }

  // Sort by session ID descending (highest first)
  const sorted = [...sessions].sort((a, b) => {
    const aId = parseInt(sessionKey(a)) || 0;
    const bId = parseInt(sessionKey(b)) || 0;
    return bId - aId;
  });

  // Default to highest session ID
  if (!currentSessionId) {
    currentSessionId = String(sessionKey(sorted[0]));
  }

  const activeSid = activeSessionFromDevice ? String(activeSessionFromDevice) : null;

  sel.innerHTML = sorted.map(s => {
    const sid = String(sessionKey(s));
    const isSelected = sid === String(currentSessionId);
    const statusText = SESSION_STATUS_MAP[s.status] || `Status ${s.status ?? "—"}`;
    const psInfo = stateLabel(s.process_state ?? s.current_state ?? null);
    const beerName = s.beer?.name || s.beer_name || "—";
    const label = `#${sid} [${statusText}] ${beerName !== "—" ? beerName : ""} ${psInfo.text} ${sid === activeSid ? "★" : ""}`.trim();
    return `<option value="${sid}" ${isSelected ? "selected" : ""}>${label}</option>`;
  }).join("");

  sel.onchange = () => {
    currentSessionId = sel.value;
    if (currentSessionId) {
      loadSessionDetail(currentSessionId);
      updateCommandButtons();
    }
  };

  if (currentSessionId) {
    loadSessionDetail(currentSessionId);
    updateCommandButtons();
  }
}

async function loadSessionDetail(sessionId) {
  const detailEmpty = document.getElementById("session-detail-empty");
  const detailContent = document.getElementById("session-detail-content");
  const fieldsEl = document.getElementById("session-detail-fields");

  if (!sessionId) {
    detailEmpty.style.display = "";
    detailContent.style.display = "none";
    return;
  }

  const session = sessionsData.find(s => String(sessionKey(s)) === String(sessionId));
  if (!session) { logWarn(`Session ${sessionId} not found in cache`); return; }

  selectedSessionDetail = session;
  detailEmpty.style.display = "none";
  detailContent.style.display = "";

  const sid = sessionKey(session);
  const psInfo = stateLabel(session.process_state ?? null);
  const uaInfo = uaLabel(session.user_action ?? null);
  const beerName = session.beer?.name || session.beer_name || "—";
  const beerStyle = session.beer?.style_name || session.beer_style || "—";
  const beerImg = session.beer?.image || null;

  let html = `<div class="sdetail-row"><span class="sdetail-label">Session ID</span><span class="sdetail-value">${sid}</span></div>`;
  html += `<div class="sdetail-row"><span class="sdetail-label">Status</span><span class="sdetail-value">${SESSION_STATUS_MAP[session.status] || session.status || "—"}</span></div>`;
  html += `<div class="sdetail-row"><span class="sdetail-label">Process State</span><span class="sdetail-value ${psInfo.cls}">${psInfo.text}</span></div>`;
  html += `<div class="sdetail-row"><span class="sdetail-label">User Action</span><span class="sdetail-value ${uaInfo.cls}">${uaInfo.text}</span></div>`;
  html += `<div class="sdetail-row"><span class="sdetail-label">Beer</span><span class="sdetail-value">${beerName}</span></div>`;
  html += `<div class="sdetail-row"><span class="sdetail-label">Style</span><span class="sdetail-value">${beerStyle}</span></div>`;
  if (session.original_gravity != null) html += `<div class="sdetail-row"><span class="sdetail-label">Original Gravity</span><span class="sdetail-value">${session.original_gravity}</span></div>`;
  if (session.device && Object.keys(session.device).length) {
    const dv = session.device;
    html += `<div class="sdetail-row"><span class="sdetail-label">Device</span><span class="sdetail-value">${dv.uuid || dv.serial_number || JSON.stringify(dv)}</span></div>`;
  }
  html += `<div class="sdetail-row"><span class="sdetail-label">Recipe ID</span><span class="sdetail-value">${session.beer_recipe_id || "—"}</span></div>`;
  if (beerImg) html += `<div class="sdetail-row"><span class="sdetail-label">Beer Image</span><span class="sdetail-value"><img src="${beerImg}" class="beer-img" alt="${beerName}"></span></div>`;
  fieldsEl.innerHTML = html;

  // Enable/disable detail delete button
  const detailDeleteBtn = document.getElementById("detail-delete-btn");
  if (detailDeleteBtn) detailDeleteBtn.disabled = false;

  // Load user action guidance if user_action is non-zero
  const ua = session.user_action;
  if (ua && ua !== 0) {
    loadUserActionSteps(sid, ua);
  } else {
    document.getElementById("user-action-panel").style.display = "none";
  }
}

async function loadUserActionSteps(sessionId, actionId) {
  const panel = document.getElementById("user-action-panel");
  const stepsEl = document.getElementById("user-action-steps");
  panel.style.display = "";
  stepsEl.innerHTML = '<div class="empty-state">Loading operator instructions…</div>';
  try {
    const resp = await fetch(`/sessions/${sessionId}/user-action/${actionId}`);
    const data = await resp.json();
    if (data.error) { stepsEl.innerHTML = `<div class="empty-state">${data.error}</div>`; return; }
    let html = `<div class="ua-title">${data.title || "—"}</div>`;
    html += `<div class="ua-desc">${data.description || ""}</div>`;
    if (data.action_steps?.length) {
      html += `<div class="ua-steps">`;
      for (const step of data.action_steps) {
        html += `<div class="ua-step">
          <div class="ua-step__order">${step.order}</div>
          <div class="ua-step__body">
            <div class="ua-step__title">${step.title}</div>
            <div class="ua-step__desc">${step.description || ""}</div>
            ${step.image ? `<img src="${step.image}" class="ua-step__img" alt="${step.title}">` : ""}
          </div>
        </div>`;
      }
      html += `</div>`;
    }
    stepsEl.innerHTML = html;
  } catch (e) {
    stepsEl.innerHTML = `<div class="empty-state">Failed to load: ${e.message}</div>`;
  }
}

// ── Command buttons ─────────────────────────────────────────────────────────

function updateCommandButtons() {
  const session = sessionsData.find(s => String(sessionKey(s)) === String(currentSessionId));
  const ua = session?.user_action ?? 0;

  const allowed = getAllowedCommands(ua);
  allowedCommands = allowed;

  const END_SESSION_BTN = document.getElementById("delete-session-btn");
  document.querySelectorAll(".control-btn[data-command]").forEach(btn => {
    const info = CMD_DEFINITIONS.find(c => c.cmd === btn.dataset.command);
    if (!info) { btn.disabled = true; return; }
    const { type } = info;
    if (info.cmd === "END_SESSION") {
      btn.disabled = !currentSessionId;
    } else if (type === 6) {
      btn.disabled = !currentSessionId || !allowed.includes(6);
    } else {
      btn.disabled = !currentSessionId || (type !== null && !allowed.includes(type));
    }
  });

  if (END_SESSION_BTN) END_SESSION_BTN.disabled = !currentSessionId;
  const tempCtrl = document.getElementById("temp-control");
  if (tempCtrl) tempCtrl.style.display = allowed.includes(6) ? "flex" : "none";
}

function getAllowedCommands(userAction) {
  const map = {
    0: [3], 12: [2, 3, 32], 13: [2, 3], 21: [2, 3], 22: [2, 3],
    23: [2, 3], 24: [2, 3], 25: [2, 3], 26: [2, 3], 27: [2, 3],
    28: [2, 3], 30: [2, 3], 31: [2, 3], 32: [2, 3], 33: [2, 3],
    34: [2, 3], 35: [2, 3], 36: [2, 3, 37], 37: [2, 3],
  };
  return map[userAction] || [3];
}

// ── Kegs ────────────────────────────────────────────────────────────────────

function renderKegs(kegs) {
  const list = document.getElementById("keg-list");
  const sel = document.getElementById("keg-select");
  if (!list) return;
  kegsData = kegs || [];
  if (!kegs || kegs.length === 0) { list.innerHTML = '<div class="empty-state">No kegs registered</div>'; return; }
  list.innerHTML = kegs.map(k => {
    const kid = k.uuid || k.id || "?";
    const name = k.display_name || k.name || kid;
    const temp = k.temperature || "—";
    return `<div class="keg-card ${kid === currentKegUuid ? "active" : ""}" data-uuid="${kid}">
      <div class="keg-card__name">${name}</div>
      <div class="keg-card__temp">${temp}°C</div>
    </div>`;
  }).join("");
  list.querySelectorAll(".keg-card").forEach(card => {
    card.addEventListener("click", () => {
      currentKegUuid = card.dataset.uuid;
      renderKegs(kegsData);
    });
  });
  if (sel) {
    sel.innerHTML = '<option value="">— select —</option>' +
      kegs.map(k => `<option value="${k.uuid || k.id}">${k.display_name || k.name || k.uuid || "Keg"}</option>`).join("");
    if (currentKegUuid) sel.value = currentKegUuid;
  }
}

// ── Recipes ─────────────────────────────────────────────────────────────────

async function loadRecipes() {
  log("Loading recipes from API…");
  try {
    const resp = await fetchWithAuth("/recipes");
    const data = await resp.json();
    if (data.error) { logError(data.error); return; }
    recipesData = data.recipes || [];
    renderRecipes(recipesData);
    logSuccess(`Loaded ${recipesData.length} recipes`);
  } catch (e) { logError(`Load recipes failed: ${e.message}`); }
}

function renderRecipes(recipes) {
  const list = document.getElementById("recipes-list");
  if (!list) return;
  if (!recipes || recipes.length === 0) { list.innerHTML = '<div class="empty-state">No recipes found</div>'; return; }
  list.innerHTML = recipes.map(r => {
    const id = r.id || r.recipe_id || "?";
    const name = r.name || r.title || `Recipe ${id}`;
    const style = r.style_name || r.beer_style || "—";
    return `<div class="recipe-card ${id === selectedRecipeId ? "active" : ""}" data-id="${id}">
      <div class="recipe-card__name">${name}</div>
      <div class="recipe-card__style">${style}</div>
    </div>`;
  }).join("");
  list.querySelectorAll(".recipe-card").forEach(card => {
    card.addEventListener("click", () => {
      selectedRecipeId = card.dataset.id;
      renderRecipes(recipesData);
      loadRecipeDetail(selectedRecipeId);
    });
  });
}

async function loadRecipeDetail(recipeId) {
  const empty = document.getElementById("recipe-detail-empty");
  const content = document.getElementById("recipe-detail-content");
  if (!recipeId) { empty.style.display = ""; content.style.display = "none"; return; }
  empty.style.display = "none";
  content.style.display = "";
  document.getElementById("recipe-detail-name").textContent = "Loading…";
  try {
    const resp = await fetch(`/recipes/${recipeId}`);
    const data = await resp.json();
    if (data.error) { logError(data.error); return; }
    const recipe = data.recipe || {};
    const steps = data.steps || [];
    document.getElementById("recipe-detail-name").textContent = recipe.name || `Recipe ${recipeId}`;
    document.getElementById("recipe-detail-style").textContent = recipe.style_name || recipe.beer_style || "—";
    const stepsList = document.getElementById("recipe-steps-list");
    if (steps.length) {
      stepsList.innerHTML = steps.map(s => `<div class="recipe-step">
        <span class="recipe-step__order">${s.order || s.step_order || ""}</span>
        <span class="recipe-step__name">${s.name || s.step_name || "—"}</span>
        <span class="recipe-step__temp">${s.temperature || s.temp || ""}°C</span>
        <span class="recipe-step__time">${s.duration || s.time || ""}min</span>
        <span class="recipe-step__desc">${s.description || ""}</span>
      </div>`).join("");
    } else {
      stepsList.innerHTML = '<div class="empty-state">No step data available</div>';
    }
    const uuidInput = document.getElementById("recipe-session-uuid");
    const startBtn = document.getElementById("start-brew-from-recipe-btn");
    if (startBtn) {
      startBtn.disabled = !uuidInput?.value;
      startBtn.onclick = () => startBrewFromRecipe(recipeId);
    }
    if (uuidInput) {
      uuidInput.addEventListener("input", () => {
        if (startBtn) startBtn.disabled = !uuidInput.value;
      });
    }
  } catch (e) { logError(`Load recipe detail failed: ${e.message}`); }
}

async function startBrewFromRecipe(recipeId) {
  const uuid = document.getElementById("recipe-session-uuid")?.value?.trim();
  if (!uuid) { logWarn("Device UUID required to start brew"); return; }
  log(`Starting brew session with recipe ${recipeId} on ${uuid}`);
  try {
    const resp = await fetchWithAuth("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_type: 0, minibrew_uuid: uuid, beer_recipe: recipeId }),
    });
    const result = await resp.json();
    if (!resp.ok) { logError(`Create failed: ${result.error || resp.status}`); return; }
    const sid = result.id || result.session_id;
    logSuccess(`Brew session created: ${sid}`);
    if (sid) { currentSessionId = String(sid); switchTab("sessions"); }
    refreshSessions();
  } catch (e) { logError(`Start brew failed: ${e.message}`); }
}

// ── Commands table ─────────────────────────────────────────────────────────

function refreshCommandsTable() {
  const tbody = document.querySelector("#commands-table tbody");
  if (!tbody) return;
  tbody.innerHTML = CMD_DEFINITIONS.map(c => {
    const uaList = c.allowedUA === "*" ? "Any" : c.allowedUA.map(u => USER_ACTION_MAP[u] || u).join(", ") || "Any";
    return `<tr>
      <td class="cmd-name">${c.cmd}</td>
      <td class="cmd-type">${c.type ?? "—"}</td>
      <td class="cmd-ua">${uaList}</td>
      <td class="cmd-desc">${c.desc}</td>
    </tr>`;
  }).join("");
}

function buildCodeTables() {
  // user_action codes
  const uaEl = document.getElementById("useraction-codes");
  if (uaEl) {
    uaEl.innerHTML = `<table class="codes-table"><thead><tr><th>ID</th><th>Label</th></tr></thead><tbody>${
      Object.entries(USER_ACTION_MAP).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")
    }</tbody></table>`;
  }
  // process_state codes
  const psEl = document.getElementById("processstate-codes");
  if (psEl) {
    psEl.innerHTML = `<table class="codes-table"><thead><tr><th>ID</th><th>State</th></tr></thead><tbody>${
      Object.entries(PROCESS_STATE_MAP).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")
    }</tbody></table>`;
  }
}

// ── Session creation form ───────────────────────────────────────────────────

function showSessionForm(type) {
  pendingSessionType = type;
  const form = document.getElementById("session-form");
  if (!form) return;
  form.style.display = "flex";
  const recipeRow = document.getElementById("session-recipe-row");
  if (recipeRow) recipeRow.style.display = type === "brew" ? "flex" : "none";
  const uuidInput = document.getElementById("session-uuid-input");
  if (uuidInput) {
    // Pre-fill with first device UUID
    uuidInput.value = allDevices[0]?.uuid || allDevices[0]?.serial_number || "";
  }
}

async function createSessionFn(sessionType, minibrewUuid, recipe) {
  log(`Creating ${sessionType} session on ${minibrewUuid}`);
  try {
    const typeMap = { brew: 0, clean: "clean_minibrew", acid_clean: "acid_clean_minibrew" };
    const resp = await fetchWithAuth("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_type: typeMap[sessionType], minibrew_uuid: minibrewUuid, beer_recipe: recipe }),
    });
    const result = await resp.json();
    if (!resp.ok) { logError(`Create failed: ${result.error || resp.status}`); return; }
    const sid = result.id || result.session_id;
    logSuccess(`Session created: ${sid}`);
    if (sid) { currentSessionId = String(sid); switchTab("sessions"); }
    document.getElementById("session-form").style.display = "none";
    refreshSessions();
  } catch (e) { logError(`Create session error: ${e.message}`); }
}

async function refreshSessions() {
  try {
    const resp = await fetchWithAuth("/sessions");
    if (!resp || !resp.ok) return;
    const data = await resp.json();
    sessionsData = data.sessions || [];
    renderSessions(sessionsData);
  } catch (e) { logError(`Refresh sessions error: ${e.message}`); }
}

// ── Device info refresh ────────────────────────────────────────────────────

async function refreshDeviceInfo() {
  log("Fetching breweryoverview…");
  try {
    const resp = await fetchWithAuth("/verify");
    if (!resp || !resp.ok) { logError(`Verify failed: ${resp?.status}`); return; }
    const data = await resp.json();
    if (data.status === "error") { logError(data.error); return; }
    logSuccess("breweryoverview OK");
    const overview = data.data;
    const selBucket = selectedBucket || document.getElementById("device-select")?.value;
    const bucket = selBucket && overview[selBucket] ? selBucket : Object.keys(overview).find(k => overview[k]?.length);
    if (bucket) {
      const dev = (overview[bucket] || [])[0];
      if (dev) updateDeviceUI({ ...dev, _raw: dev });
    }
    const rawEl = document.getElementById("info-raw-json");
    if (rawEl) rawEl.textContent = prettyJson(overview);
  } catch (e) { logError(`Verify failed: ${e.message}`); }
}

// ── Auto-refresh ────────────────────────────────────────────────────────────

function startAutoRefresh(seconds) {
  stopAutoRefresh();
  if (seconds === 0) return;
  autoRefreshSeconds = seconds;
  log(`Auto-refresh: ${seconds}s`);
  autoRefreshInterval = setInterval(() => {
    if (activeSource === "overview") refreshDeviceInfo();
  }, seconds * 1000);
}

function stopAutoRefresh() {
  if (autoRefreshInterval) { clearInterval(autoRefreshInterval); autoRefreshInterval = null; }
}

// ── API calls ───────────────────────────────────────────────────────────────

async function sendCommand(command, params) {
  if (!currentSessionId) { logWarn("No session selected"); return; }
  try {
    log(`Sending: ${command} ${params ? JSON.stringify(params) : ""}`);
    const resp = await fetch(`/session/${currentSessionId}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params }),
    });
    const result = await resp.json();
    if (!resp.ok) logError(`Command failed: ${result.error || resp.status}`);
    else logSuccess(`Command ${command} sent`);
  } catch (e) { logError(`Command error: ${e.message}`); }
}

async function sendKegCommand(kegUuid, command, params) {
  try {
    log(`Keg ${kegUuid}: ${command}`);
    const resp = await fetch(`/keg/${kegUuid}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params }),
    });
    const result = await resp.json();
    if (!resp.ok) logError(`Keg command failed: ${result.error || resp.status}`);
    else logSuccess(`Keg command ${command} sent`);
  } catch (e) { logError(`Keg command error: ${e.message}`); }
}

function switchTab(name) {
  document.querySelectorAll(".navbar__tab").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach(p => {
    p.classList.toggle("active", p.id === `tab-${name}`);
  });
}

// ── Token gate ──────────────────────────────────────────────────────────────

let tokenGatePassed = false;

async function checkTokenAndGate() {
  try {
    const resp = await fetchWithAuth("/settings/token");
    if (!resp || !resp.ok) throw new Error();
    const data = await resp.json();
    if (data.token_set) {
      tokenGatePassed = true;
      document.getElementById("token-gate").style.display = "none";
      connect();
    } else {
      document.getElementById("token-gate").style.display = "flex";
    }
  } catch {
    document.getElementById("token-gate").style.display = "flex";
  }
}

// ── Auth init ───────────────────────────────────────────────────────────────

async function initAuth() {
  const token = getJwtToken();
  if (!token) { showAuthGate(); return; }
  try {
    const resp = await fetchWithAuth("/auth/me");
    if (!resp) { showAuthGate(); return; }
    if (resp.ok) {
      const user = await resp.json();
      showDashboard(user);
    } else {
      showAuthGate();
    }
  } catch {
    showAuthGate();
  }
}

async function doLogin(username, password) {
  const resp = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await resp.json();
  if (!resp.ok) return { error: data.detail || "Login failed" };
  setJwtToken(data.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
  return { user: data.user };
}

async function doRegister(username, password, confirmPassword) {
  if (password !== confirmPassword) return { error: "Passwords do not match" };
  const resp = await fetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await resp.json();
  if (!resp.ok) return { error: data.detail || "Registration failed" };
  setJwtToken(data.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
  return { user: data.user };
}

function doLogout() {
  clearJwtToken();
  showAuthGate();
}

// ── Settings modal ──────────────────────────────────────────────────────────

function openSettingsModal() {
  document.getElementById("settings-modal").style.display = "flex";
  document.getElementById("settings-token-input").value = "";
  loadTokenStatus();
}
function closeSettingsModal() {
  document.getElementById("settings-modal").style.display = "none";
}

async function loadTokenStatus() {
  try {
    const resp = await fetchWithAuth("/settings/token");
    if (resp && resp.ok) {
      const data = await resp.json();
      updateTokenStatusUI(data.token_set, data.source);
    }
  } catch {}
}

function updateTokenStatusUI(isSet, source) {
  const el = document.getElementById("settings-token-status");
  const srcEl = document.getElementById("settings-token-source");
  if (!el) return;
  if (isSet) {
    el.innerHTML = '<span class="token-indicator token-indicator--set">Token active</span>';
    if (srcEl) srcEl.textContent = source === "env" ? "Source: .env file" : source === "stored" ? "Source: encrypted storage" : "";
  } else {
    el.innerHTML = '<span class="token-indicator token-indicator--unset">Not set</span>';
    if (srcEl) srcEl.textContent = "No token — enter one below";
  }
}

// ── Event bindings ──────────────────────────────────────────────────────────

function bindEvents() {

  // ── Auth ──────────────────────────────────────────────────────────────────
  document.querySelectorAll(".auth-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".auth-tab").forEach(b => b.classList.toggle("active", b === btn));
      document.getElementById("auth-login-form").style.display = tab === "login" ? "" : "none";
      document.getElementById("auth-register-form").style.display = tab === "register" ? "" : "none";
      document.getElementById("auth-error").style.display = "none";
    });
  });

  document.getElementById("login-submit-btn")?.addEventListener("click", async () => {
    const u = document.getElementById("login-username")?.value?.trim();
    const p = document.getElementById("login-password")?.value;
    const err = document.getElementById("auth-error");
    if (!u || !p) { err.textContent = "Username and password required"; err.style.display = ""; return; }
    const result = await doLogin(u, p);
    if (result.error) { err.textContent = result.error; err.style.display = ""; }
    else { showDashboard(result.user); }
  });

  document.getElementById("register-submit-btn")?.addEventListener("click", async () => {
    const u = document.getElementById("register-username")?.value?.trim();
    const p = document.getElementById("register-password")?.value;
    const c = document.getElementById("register-confirm")?.value;
    const err = document.getElementById("auth-error");
    if (!u || !p) { err.textContent = "Username and password required"; err.style.display = ""; return; }
    const result = await doRegister(u, p, c);
    if (result.error) { err.textContent = result.error; err.style.display = ""; }
    else { showDashboard(result.user); }
  });

  document.getElementById("navbar-logout-btn")?.addEventListener("click", doLogout);
  document.getElementById("logout-btn")?.addEventListener("click", doLogout);

  document.getElementById("login-password")?.addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("login-submit-btn")?.click(); });
  document.getElementById("register-password")?.addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("register-submit-btn")?.click(); });

  // Device dropdown
  document.getElementById("device-select")?.addEventListener("change", onDeviceSelectChange);

  // Tab nav
  initTabs();

  // Refresh button
  document.getElementById("refresh-device-btn")?.addEventListener("click", () => { activeSource = "overview"; refreshDeviceInfo(); });

  // Auto-refresh select
  document.getElementById("auto-refresh-select")?.addEventListener("change", (e) => {
    const val = parseInt(e.target.value);
    if (val === 0) stopAutoRefresh(); else startAutoRefresh(val);
  });
  startAutoRefresh(autoRefreshSeconds);

  // Command buttons
  document.querySelectorAll(".control-btn[data-command]").forEach(btn => {
    btn.addEventListener("click", () => {
      const cmd = btn.dataset.command;
      if (cmd === "END_SESSION") {
        if (!currentSessionId) return;
        fetch(`/sessions/${currentSessionId}/wake-then-delete`, { method: "POST" })
          .then(r => { if (r.ok) { currentSessionId = null; refreshSessions(); logSuccess("Session deleted"); } else logError("Delete failed"); } )
          .catch(e => logError(e.message));
        return;
      }
      if (cmd === "CHANGE_TEMPERATURE") {
        const temp = parseFloat(document.getElementById("temp-input")?.value);
        sendCommand(cmd, { serving_temperature: temp });
        return;
      }
      sendCommand(cmd);
    });
  });

  // Temp apply
  document.getElementById("temp-apply-btn")?.addEventListener("click", () => {
    const temp = parseFloat(document.getElementById("temp-input")?.value);
    if (!isNaN(temp)) sendCommand("CHANGE_TEMPERATURE", { serving_temperature: temp });
  });

  // Delete session (status section)
  document.getElementById("delete-session-btn")?.addEventListener("click", () => {
    if (!currentSessionId) return;
    fetch(`/sessions/${currentSessionId}/wake-then-delete`, { method: "POST" })
      .then(r => { if (r.ok) { currentSessionId = null; refreshSessions(); logSuccess("Session deleted"); } else logError("Delete failed"); } )
      .catch(e => logError(e.message));
  });

  // Session detail delete
  document.getElementById("detail-delete-btn")?.addEventListener("click", () => {
    if (!currentSessionId) return;
    fetch(`/sessions/${currentSessionId}/wake-then-delete`, { method: "POST" })
      .then(r => { if (r.ok) { currentSessionId = null; selectedSessionDetail = null; refreshSessions();
        document.getElementById("session-detail-empty").style.display = "";
        document.getElementById("session-detail-content").style.display = "none";
        logSuccess("Session deleted"); } else logError("Delete failed"); } )
      .catch(e => logError(e.message));
  });

  // Create session buttons
  document.getElementById("create-brew-btn")?.addEventListener("click", () => showSessionForm("brew"));
  document.getElementById("create-clean-btn")?.addEventListener("click", () => showSessionForm("clean"));
  document.getElementById("create-acid-btn")?.addEventListener("click", () => showSessionForm("acid_clean"));
  document.getElementById("session-form-cancel-btn")?.addEventListener("click", () => {
    document.getElementById("session-form").style.display = "none";
    pendingSessionType = null;
  });
  document.getElementById("session-form-create-btn")?.addEventListener("click", () => {
    const uuid = document.getElementById("session-uuid-input")?.value?.trim();
    if (!uuid) { logWarn("Device UUID required"); return; }
    let recipe = null;
    if (pendingSessionType === "brew") {
      const raw = document.getElementById("session-recipe-input")?.value?.trim();
      if (raw) { const parsed = parseInt(raw); if (!isNaN(parsed)) recipe = parsed; }
    }
    createSessionFn(pendingSessionType, uuid, recipe);
  });

  // Load recipes
  document.getElementById("load-recipes-btn")?.addEventListener("click", loadRecipes);

  // Keg select
  document.getElementById("keg-select")?.addEventListener("change", (e) => {
    currentKegUuid = e.target.value || null;
    const tempBtn = document.querySelector(".keg-action-btn[data-action='SET_KEG_TEMPERATURE']");
    const tempRow = document.getElementById("keg-temp-row");
    if (tempBtn) tempBtn.disabled = !currentKegUuid;
    if (tempRow) tempRow.style.display = currentKegUuid ? "flex" : "none";
    renderKegs(kegsData);
  });

  // Keg name
  document.getElementById("set-beer-name-btn")?.addEventListener("click", async () => {
    const name = document.getElementById("beer-name-input")?.value?.trim();
    if (!currentKegUuid || !name) return;
    try {
      const resp = await fetch(`/keg/${currentKegUuid}/display-name`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: name }),
      });
      const r = await resp.json();
      if (!resp.ok) logError(`Failed: ${r.error || resp.status}`); else logSuccess(`Beer name set to "${name}"`);
    } catch (e) { logError(e.message); }
  });

  // Keg action buttons
  document.querySelectorAll(".keg-action-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      if (!currentKegUuid) { logWarn("Select a keg first"); return; }
      const action = btn.dataset.action;
      if (action === "SET_KEG_TEMPERATURE") {
        const temp = parseFloat(document.getElementById("keg-temp-input")?.value);
        if (isNaN(temp)) return;
        sendKegCommand(currentKegUuid, action, { temperature: temp });
      } else {
        sendKegCommand(currentKegUuid, action);
      }
    });
  });

  // Settings modal
  document.getElementById("settings-btn")?.addEventListener("click", openSettingsModal);
  document.getElementById("settings-close-btn")?.addEventListener("click", closeSettingsModal);
  document.getElementById("settings-overlay")?.addEventListener("click", closeSettingsModal);
  document.getElementById("settings-save-btn")?.addEventListener("click", async () => {
    const token = document.getElementById("settings-token-input")?.value?.trim();
    if (!token) { logWarn("Token cannot be empty"); return; }
    const btn = document.getElementById("settings-save-btn");
    btn.disabled = true; btn.textContent = "Saving…";
    try {
      const resp = await fetchWithAuth("/settings/token", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const result = await resp.json();
      if (!resp.ok) logError(`Save failed: ${result.error || resp.status}`);
      else {
        logSuccess("Token saved — reconnecting…");
        updateTokenStatusUI(true, "stored");
        closeSettingsModal();
        setTimeout(() => { if (ws) ws.close(); connect(); }, 500);
      }
    } catch (e) { logError(e.message); }
    finally { btn.disabled = false; btn.textContent = "Save & Apply"; }
  });
  document.getElementById("settings-reset-btn")?.addEventListener("click", async () => {
    try {
      await fetchWithAuth("/settings/token", { method: "DELETE" });
      logSuccess("Token reset — reconnecting…");
      updateTokenStatusUI(false, null);
      closeSettingsModal();
      setTimeout(() => { if (ws) ws.close(); connect(); }, 500);
    } catch { logError("Reset failed"); }
  });

  // Token gate
  document.getElementById("gate-submit-btn")?.addEventListener("click", async () => {
    const token = document.getElementById("gate-token-input")?.value?.trim();
    if (!token) {
      const err = document.getElementById("gate-error");
      err.textContent = "Token cannot be empty"; err.style.display = "block"; return;
    }
    const err = document.getElementById("gate-error");
    err.style.display = "none";
    try {
      const resp = await fetchWithAuth("/settings/token", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!resp || !resp.ok) {
        const result = await resp?.json();
        err.textContent = result?.error || "Failed"; err.style.display = "block";
      } else {
        err.style.display = "none";
        tokenGatePassed = true;
        document.getElementById("token-gate").style.display = "none";
        connect();
      }
    } catch (e) { err.textContent = `Error: ${e.message}`; err.style.display = "block"; }
  });
  document.getElementById("gate-token-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("gate-submit-btn")?.click();
  });

  // Console
  document.getElementById("suppress-ws-logs")?.addEventListener("change", (e) => {
    suppressWsLogs = e.target.checked;
  });
  document.getElementById("clear-log-btn")?.addEventListener("click", () => {
    const el = document.getElementById("log-output");
    if (el) el.innerHTML = "";
  });
}

// ── Boot ────────────────────────────────────────────────────────────────────

let pendingSessionType = null;

bindEvents();
initAuth();
