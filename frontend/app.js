const WS_BASE = window.location.hostname === "localhost" ? "ws://localhost:8000" : `ws://${window.location.host}`;
let ws = null;
let currentSessionId = null;
let currentKegUuid = null;
let allowedCommands = [];
let kegsData = [];
let pendingSessionType = null;
let activeSource = "overview";
let autoRefreshInterval = null;
let autoRefreshSeconds = 0;
let suppressWsLogs = true;

function log(msg, type = "info") {
  // Suppress WebSocket connect/disconnect noise when enabled.
  if (suppressWsLogs && (type === "info" || type === "warn")) {
    if (msg.includes("WebSocket connected") || msg.includes("WebSocket disconnected")) return;
  }
  const el = document.getElementById("log-output");
  if (!el) return;
  const entry = document.createElement("div");
  entry.className = `log-entry log-entry--${type}`;
  const time = new Date().toLocaleTimeString();
  entry.textContent = `[${time}] ${msg}`;
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
}
function logError(msg) { log(msg, "error"); }
function logSuccess(msg) { log(msg, "success"); }
function logWarn(msg) { log(msg, "warn"); }

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
    else if (msg.type === "system_event") handleSystemEvent(msg);
  };
}

function handleInitialState(payload) {
  renderSessions(payload.sessions || []);
  renderKegs(payload.kegs || []);
  if (payload.device) {
    updateDeviceUI(payload.device);
    if (payload.device._raw) displayRawJson(payload.device._raw);
  }
}

function handleDeviceUpdate(payload) {
  if (payload.sessions) renderSessions(payload.sessions);
  if (payload.kegs) renderKegs(payload.kegs);
}

function handleSessionUpdate(payload) {
  renderSessions(payload.sessions ? [payload] : []);
}

function handleSystemEvent(msg) {
  log(`System event: ${msg.payload ? JSON.stringify(msg.payload) : msg.type}`, "warn");
}

function prettyJson(obj) {
  return JSON.stringify(obj, null, 2);
}

function displayRawJson(data) {
  const el = document.getElementById("info-raw-json");
  if (el) el.textContent = prettyJson(data);
}

function fmt(v) {
  return v == null || v === "" ? null : v;
}

function setField(id, value, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value;
  el.className = "device-field__value";
  if (cls) el.classList.add(cls);
}

function label(name, value, cls) {
  const el = document.getElementById(`info-${name}`);
  if (!el) return;
  el.textContent = value;
  el.className = `device-field__value${cls ? " " + cls : ""}`;
}

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

const PROCESS_TYPE_MAP = { 0: "Brewing", 1: "Cleaning", 2: "Fermentation" };
const DEVICE_TYPE_MAP = { 0: "Standard", 1: "Brew", 2: "Keg", 3: "Climate" };
const CONNECTION_STATUS_MAP = { 0: "Offline", 1: "Online" };

const PHASE_MAP = {
  24: "BREWING", 30: "BREWING", 31: "BREWING", 40: "BREWING",
  50: "BREWING", 51: "BREWING", 52: "BREWING", 60: "BREWING",
  70: "BREWING", 71: "BREWING", 74: "BREWING",
  75: "FERMENTATION", 80: "FERMENTATION", 84: "FERMENTATION",
  88: "SERVING", 90: "SERVING", 91: "SERVING", 92: "SERVING", 93: "SERVING",
  101: "CLEANING", 103: "CLEANING", 108: "CLEANING", 109: "CLEANING",
  111: "CLEANING", 112: "CLEANING", 113: "CLEANING", 114: "CLEANING",
};

const FAILURE_STATES = [71, 84, 93, 109];

function stateLabel(v, fallback) {
  if (v == null) return { text: fallback || "—", cls: "device-field__value--null" };
  const known = PROCESS_STATE_MAP[v];
  if (known) return { text: `${v} (${known})`, cls: "device-field__value--code" };
  return { text: `${v} (NULL)`, cls: "device-field__value--null" };
}

function uaLabel(v) {
  if (v == null) return { text: "—", cls: "" };
  const known = USER_ACTION_MAP[v];
  if (known) return { text: `${v} (${known})`, cls: "device-field__value--code" };
  return { text: `${v} (NULL)`, cls: "device-field__value--null" };
}

function boolLabel(v) {
  if (v == null) return "—";
  return v ? "Yes" : "No";
}

function phaseOf(state) {
  return PHASE_MAP[state] || null;
}

function renderBreweryOverview(payload) {
  let firstDevice = null;
  for (const key of ["brew_clean_idle", "fermenting", "serving", "brew_acid_clean_idle"]) {
    const list = payload[key];
    if (list && list.length > 0) { firstDevice = list[0]; break; }
  }

  const uuid = firstDevice ? (firstDevice.uuid || firstDevice.serial_number || null) : null;
  const ps = firstDevice?.process_state ?? null;
  const stateInfo = stateLabel(ps);
  const uaInfo = uaLabel(firstDevice?.user_action ?? null);
  const phase = phaseOf(ps);
  const isFail = FAILURE_STATES.includes(ps);

  updateUuidDisplay(uuid);

  label("uuid", uuid ?? "null", uuid ? "device-field__value--uuid" : "device-field__value--null");
  label("custom-name", firstDevice?.title ?? "—");
  label("serial-number", firstDevice?.serial_number ?? "—");

  label("current-state", firstDevice?.current_state != null ? `${firstDevice.current_state} (${PROCESS_STATE_MAP[firstDevice.current_state] || "NULL"})` : "—",
    firstDevice?.current_state != null && !PROCESS_STATE_MAP[firstDevice.current_state] ? "device-field__value--null" : "");

  label("process-type", firstDevice?.process_type != null
    ? `${firstDevice.process_type} (${PROCESS_TYPE_MAP[firstDevice.process_type] || "Unknown"})`
    : "—",
    firstDevice?.process_type != null && !PROCESS_TYPE_MAP[firstDevice.process_type] ? "device-field__value--null" : "");

  label("process-state", stateInfo.text, stateInfo.cls);
  label("user-action", uaInfo.text, uaInfo.cls);

  label("stage", firstDevice?.stage ?? "—");

  label("sub-title", firstDevice?.sub_title ?? "—");
  label("current-temp", firstDevice?.current_temp != null ? `${firstDevice.current_temp}°C` : "—");
  label("target-temp", firstDevice?.target_temp != null ? `${firstDevice.target_temp}°C` : "—");
  label("gravity", firstDevice?.gravity ?? "—");
  label("beer-name", firstDevice?.beer_name ?? "—");
  label("beer-style", firstDevice?.beer_style ?? "—");
  label("session-id", firstDevice?.session_id ?? "—");
  label("active-session", firstDevice?.active_session ?? "—");
  label("software-version", firstDevice?.software_version ?? "—");
  label("device-type", firstDevice?.device_type != null
    ? `${firstDevice.device_type} (${DEVICE_TYPE_MAP[firstDevice.device_type] || "Unknown"})`
    : "—",
    firstDevice?.device_type != null && !DEVICE_TYPE_MAP[firstDevice.device_type] ? "device-field__value--null" : "");

  label("online", firstDevice?.online != null ? boolLabel(firstDevice.online) : "—");
  label("updating", firstDevice?.updating != null ? boolLabel(firstDevice.updating) : "—");
  label("needs-acid-cleaning", firstDevice?.needs_acid_cleaning != null ? boolLabel(firstDevice.needs_acid_cleaning) : "—");
  label("last-online", "—");
  label("last-state-change", "—");

  const headerStateEl = document.getElementById("process-state");
  const headerPhaseEl = document.getElementById("phase-label");
  if (headerStateEl) headerStateEl.textContent = isFail ? `FAIL: ${stateInfo.text}` : stateInfo.text;
  if (headerPhaseEl) headerPhaseEl.textContent = phase ? `[${phase}]` : "—";

  return uuid;
}

function renderDevices(payload) {
  const devices = payload.devices || [];
  const first = devices[0] || null;
  const uuid = first ? (first.uuid || first.serial_number || null) : null;
  const ps = first?.process_state ?? null;
  const stateInfo = stateLabel(ps);
  const uaInfo = uaLabel(first?.user_action ?? null);
  const phase = phaseOf(ps);
  const isFail = FAILURE_STATES.includes(ps);

  updateUuidDisplay(uuid);

  label("uuid", uuid ?? "null", uuid ? "device-field__value--uuid" : "device-field__value--null");
  label("custom-name", first?.custom_name ?? "—");
  label("serial-number", first?.serial_number ?? "—");

  label("current-state", first?.current_state != null
    ? `${first.current_state} (${PROCESS_STATE_MAP[first.current_state] || "NULL"})`
    : "—",
    first?.current_state != null && !PROCESS_STATE_MAP[first.current_state] ? "device-field__value--null" : "");

  label("process-type", first?.process_type != null
    ? `${first.process_type} (${PROCESS_TYPE_MAP[first.process_type] || "Unknown"})`
    : "—",
    first?.process_type != null && !PROCESS_TYPE_MAP[first.process_type] ? "device-field__value--null" : "");

  label("process-state", stateInfo.text, stateInfo.cls);
  label("user-action", uaInfo.text, uaInfo.cls);
  label("stage", first?.text ?? "—");
  label("sub-title", "—");
  label("current-temp", "—");
  label("target-temp", "—");
  label("gravity", "—");
  label("beer-name", "—");
  label("beer-style", "—");
  label("session-id", "—");
  label("active-session", first?.active_session ?? "—");
  label("software-version", first?.software_version ?? "—");
  label("device-type", first?.device_type != null
    ? `${first.device_type} (${DEVICE_TYPE_MAP[first.device_type] || "Unknown"})`
    : "—",
    first?.device_type != null && !DEVICE_TYPE_MAP[first.device_type] ? "device-field__value--null" : "");

  const connStatus = first?.connection_status ?? null;
  label("online", connStatus != null
    ? `${connStatus} (${CONNECTION_STATUS_MAP[connStatus] || "Unknown"})`
    : "—",
    connStatus === 1 ? "device-field__value--green" : (connStatus === 0 ? "device-field__value--null" : ""));

  label("updating", first?.updating != null ? boolLabel(first.updating) : "—");
  label("needs-acid-cleaning", "—");
  label("last-online", first?.last_time_online ? formatDate(first.last_time_online) : "—");
  label("last-state-change", first?.last_process_state_change ? formatDate(first.last_process_state_change) : "—");

  const headerStateEl = document.getElementById("process-state");
  const headerPhaseEl = document.getElementById("phase-label");
  if (headerStateEl) headerStateEl.textContent = isFail ? `FAIL: ${stateInfo.text}` : stateInfo.text;
  if (headerPhaseEl) headerPhaseEl.textContent = phase ? `[${phase}]` : "—";

  return uuid;
}

function formatDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

async function refreshDeviceInfo() {
  log("Fetching /verify (breweryoverview)...");
  try {
    const resp = await fetch("/verify");
    if (!resp.ok) { logError(`Verify failed (${resp.status}): ${await resp.text()}`); return; }
    const data = await resp.json();
    if (data.status === "error") { logError(`breweryoverview error: ${data.error}`); displayRawJson({error: data.error}); return; }
    logSuccess("breweryoverview fetched OK");
    const uuid = renderBreweryOverview(data.data);
    displayRawJson(data.data);
    log(`breweryoverview — UUID: ${uuid ?? "null"}`);
  } catch (e) { logError(`Verify request failed: ${e.message}`); }
}

async function refreshDevices() {
  log("Fetching /devices (v1/devices)...");
  try {
    const resp = await fetch("/devices");
    if (!resp.ok) { logError(`Devices failed (${resp.status}): ${await resp.text()}`); return; }
    const data = await resp.json();
    if (data.status === "error") { logError(`Devices API error: ${data.error}`); displayRawJson({error: data.error}); return; }
    logSuccess(`/devices returned ${data.devices?.length ?? 0} device(s)`);
    const uuid = renderDevices(data);
    displayRawJson({devices: data.devices});
    log(`v1/devices — UUID: ${uuid ?? "null"}`);
  } catch (e) { logError(`Devices request failed: ${e.message}`); }
}

function updateUuidDisplay(uuid) {
  const headerEl = document.getElementById("device-uuid");
  if (headerEl) {
    if (uuid) {
      headerEl.textContent = `UUID: ${uuid}`;
      headerEl.style.color = "";
      headerEl.classList.remove("status-bar__uuid--null");
    } else {
      headerEl.textContent = "UUID: null";
      headerEl.style.color = "#ef4444";
      headerEl.classList.add("status-bar__uuid--null");
    }
  }
  const infoEl = document.getElementById("info-uuid");
  if (infoEl) {
    infoEl.textContent = uuid ?? "null";
    infoEl.style.color = uuid ? "" : "#ef4444";
    infoEl.classList.toggle("device-field__value--null", !uuid);
  }
}

function setActiveSource(source) {
  activeSource = source;
  document.querySelectorAll(".refresh-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.source === source);
  });
  if (autoRefreshSeconds > 0) startAutoRefresh(autoRefreshSeconds);
}

function startAutoRefresh(seconds) {
  stopAutoRefresh();
  if (seconds === 0) return;
  autoRefreshSeconds = seconds;
  const label = document.querySelector("#auto-refresh-select option[value='" + seconds + "']");
  const labelText = label ? label.textContent : `${seconds}s`;
  log(`Auto-refresh enabled: ${labelText}`);
  autoRefreshInterval = setInterval(() => {
    if (activeSource === "overview") refreshDeviceInfo();
    else refreshDevices();
  }, seconds * 1000);
}

function stopAutoRefresh() {
  if (autoRefreshInterval) { clearInterval(autoRefreshInterval); autoRefreshInterval = null; }
  autoRefreshSeconds = 0;
}

function renderSessions(sessions) {
  const list = document.getElementById("sessions-list");
  if (!sessions || sessions.length === 0) { list.innerHTML = '<div class="empty-state">No active sessions</div>'; return; }
  list.innerHTML = sessions.map(s => `
    <div class="session-card ${s.id === currentSessionId ? "active" : ""}" data-id="${s.id}">
      <div class="session-card__id">${s.id}</div>
      <div class="session-card__state">${s.process_state ?? s.current_state ?? "—"}</div>
      <div class="session-card__label">${s.stage || s.text || ""}</div>
    </div>
  `).join("");
  list.querySelectorAll(".session-card").forEach(card => {
    card.addEventListener("click", () => {
      currentSessionId = card.dataset.id;
      renderSessions(sessions);
      updateCommandButtonsFromSession();
    });
  });
  if (sessions.length === 1 && !currentSessionId) {
    currentSessionId = sessions[0].id;
    renderSessions(sessions);
    updateCommandButtonsFromSession();
  }
}

function updateCommandButtonsFromSession() {
  const session = sessionsData.find(s => s.id === currentSessionId);
  if (!session) return;
  const ua = session.user_action ?? 0;
  const allowed = getAllowedCommands(ua);
  allowedCommands = allowed;
  const CMD_MAP = {
    "END_SESSION": { cmd: "END_SESSION", type: null },
    "NEXT_STEP": { cmd: "NEXT_STEP", type: 3 },
    "BYPASS_USER_ACTION": { cmd: "BYPASS_USER_ACTION", type: 3 },
    "CHANGE_TEMPERATURE": { cmd: "CHANGE_TEMPERATURE", type: 6 },
    "GO_TO_MASH": { cmd: "GO_TO_MASH", type: 3 },
    "GO_TO_BOIL": { cmd: "GO_TO_BOIL", type: 3 },
    "FINISH_BREW_SUCCESS": { cmd: "FINISH_BREW_SUCCESS", type: 3 },
    "FINISH_BREW_FAILURE": { cmd: "FINISH_BREW_FAILURE", type: 3 },
    "CLEAN_AFTER_BREW": { cmd: "CLEAN_AFTER_BREW", type: 3 },
    "BYPASS_CLEAN": { cmd: "BYPASS_CLEAN", type: 3 },
  };
  document.querySelectorAll(".control-btn").forEach(btn => {
    const info = CMD_MAP[btn.dataset.command];
    if (!info) { btn.disabled = true; return; }
    const { type } = info;
    btn.disabled = !currentSessionId || (type !== null && !allowed.includes(type));
  });
  document.getElementById("temp-control").style.display = allowed.includes(6) ? "flex" : "none";
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

let sessionsData = [];

function renderKegs(kegs) {
  kegsData = kegs;
  const list = document.getElementById("keg-list");
  const select = document.getElementById("keg-select");
  if (select) {
    select.innerHTML = '<option value="">— select keg —</option>' +
      kegs.map(k => `<option value="${k.uuid || k.id}">${k.display_name || k.name || k.uuid || "Keg"}</option>`).join("");
    if (currentKegUuid) select.value = currentKegUuid;
  }
  if (!kegs || kegs.length === 0) { list.innerHTML = '<div class="empty-state">No kegs registered</div>'; return; }
  list.innerHTML = kegs.map(k => `
    <div class="keg-card ${(k.uuid || k.id) === currentKegUuid ? "active" : ""}" data-uuid="${k.uuid || k.id}">
      <div class="keg-card__header">
        <span class="keg-card__name">${k.display_name || k.name || k.uuid || "—"}</span>
        <span class="keg-card__temp">${k.temperature ? k.temperature + "°C" : "—"}</span>
      </div>
      <div class="keg-card__mode">${k.mode || "—"}</div>
    </div>
  `).join("");
  list.querySelectorAll(".keg-card").forEach(card => {
    card.addEventListener("click", () => {
      currentKegUuid = card.dataset.uuid;
      renderKegs(kegs);
    });
  });
}

function updateDeviceUI(device) {
  updateUuidDisplay(device.uuid);
  const raw = device._raw;
  if (raw && raw.brew_clean_idle) renderBreweryOverview(raw);
  else if (raw && raw.devices) renderDevices(raw);
}

async function sendCommand(command, params) {
  if (!currentSessionId) { logWarn("No session selected"); return; }
  try {
    log(`Sending session command: ${command} ${params ? JSON.stringify(params) : ""}`);
    const resp = await fetch(`/session/${currentSessionId}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params }),
    });
    const result = await resp.json();
    if (!resp.ok) logError(`Command failed: ${result.error || resp.status}`);
    else logSuccess(`Command ${command} sent OK`);
  } catch (e) { logError(`Command error: ${e.message}`); }
}

async function sendKegCommand(kegUuid, command, params) {
  try {
    log(`Sending keg command: ${command} ${params ? JSON.stringify(params) : ""}`);
    const resp = await fetch(`/keg/${kegUuid}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params }),
    });
    const result = await resp.json();
    if (!resp.ok) logError(`Keg command failed: ${result.error || resp.status}`);
    else logSuccess(`Keg command ${command} sent OK`);
  } catch (e) { logError(`Keg command error: ${e.message}`); }
}

async function createSession(sessionType, minibrewUuid, recipe) {
  log(`Creating session: ${sessionType} for ${minibrewUuid}`);
  try {
    const resp = await fetch("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_type: sessionType, minibrew_uuid: minibrewUuid, beer_recipe: recipe }),
    });
    const result = await resp.json();
    if (!resp.ok) { logError(`Create session failed: ${result.error || resp.status}`); return; }
    logSuccess(`Session created: ${result.id || result.session_id || JSON.stringify(result)}`);
    const id = result.id || result.session_id;
    if (id) { currentSessionId = String(id); refreshSessions(); }
  } catch (e) { logError(`Create session error: ${e.message}`); }
}

async function refreshSessions() {
  try {
    const resp = await fetch("/sessions");
    if (!resp.ok) return;
    const data = await resp.json();
    sessionsData = data.sessions || [];
    renderSessions(sessionsData);
    if (currentSessionId) updateCommandButtonsFromSession();
  } catch (e) { logError(`Refresh sessions error: ${e.message}`); }
}

const CMD_MAP = {
  "END_SESSION": "END_SESSION", "NEXT_STEP": "NEXT_STEP", "BYPASS_USER_ACTION": "BYPASS_USER_ACTION",
  "CHANGE_TEMPERATURE": "CHANGE_TEMPERATURE", "GO_TO_MASH": "GO_TO_MASH", "GO_TO_BOIL": "GO_TO_BOIL",
  "FINISH_BREW_SUCCESS": "FINISH_BREW_SUCCESS", "FINISH_BREW_FAILURE": "FINISH_BREW_FAILURE",
  "CLEAN_AFTER_BREW": "CLEAN_AFTER_BREW", "BYPASS_CLEAN": "BYPASS_CLEAN",
};

document.querySelectorAll(".control-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const cmd = CMD_MAP[btn.dataset.command];
    if (cmd === "END_SESSION") {
      if (!currentSessionId) return;
      log(`Deleting session ${currentSessionId}`);
      fetch(`/sessions/${currentSessionId}`, { method: "DELETE" })
        .then(r => { if (r.ok) { currentSessionId = null; refreshSessions(); logSuccess("Session deleted"); } else logError("Delete failed"); })
        .catch(e => logError(`Delete error: ${e.message}`));
      return;
    }
    if (cmd) sendCommand(cmd);
  });
});

document.getElementById("temp-apply-btn")?.addEventListener("click", () => {
  const temp = parseFloat(document.getElementById("temp-input")?.value);
  if (!isNaN(temp)) sendCommand("CHANGE_TEMPERATURE", { serving_temperature: temp });
});

document.getElementById("keg-select")?.addEventListener("change", (e) => {
  currentKegUuid = e.target.value || null;
  if (currentKegUuid) renderKegs(kegsData);
});

document.getElementById("set-beer-name-btn")?.addEventListener("click", async () => {
  const name = document.getElementById("beer-name-input")?.value?.trim();
  if (!currentKegUuid || !name) return;
  log(`Setting beer name: "${name}"`);
  try {
    const resp = await fetch(`/keg/${currentKegUuid}/display-name`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: name }),
    });
    const result = await resp.json();
    if (!resp.ok) logError(`Set name failed: ${result.error || resp.status}`);
    else logSuccess(`Beer name set to "${name}"`);
  } catch (e) { logError(`Set name error: ${e.message}`); }
});

document.getElementById("set-keg-temp-btn")?.addEventListener("click", () => {
  if (!currentKegUuid) { logWarn("No keg selected"); return; }
  const temp = parseFloat(document.getElementById("keg-temp-input")?.value);
  if (isNaN(temp)) return;
  log(`Setting keg temperature: ${temp}°C`);
  sendKegCommand(currentKegUuid, "SET_KEG_TEMPERATURE", { temperature: temp });
});

document.querySelectorAll(".keg-action-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    if (!currentKegUuid) { logWarn("No keg selected"); return; }
    sendKegCommand(currentKegUuid, btn.dataset.action);
  });
});

document.getElementById("create-brew-btn")?.addEventListener("click", () => {
  pendingSessionType = "brew";
  document.getElementById("session-form").style.display = "flex";
  document.getElementById("session-recipe-input").parentElement.style.display = "flex";
});

document.getElementById("create-clean-btn")?.addEventListener("click", () => {
  pendingSessionType = "clean";
  document.getElementById("session-form").style.display = "flex";
  document.getElementById("session-recipe-input").parentElement.style.display = "none";
});

document.getElementById("create-acid-btn")?.addEventListener("click", () => {
  pendingSessionType = "acid_clean";
  document.getElementById("session-form").style.display = "flex";
  document.getElementById("session-recipe-input").parentElement.style.display = "none";
});

document.getElementById("session-form-cancel-btn")?.addEventListener("click", () => {
  document.getElementById("session-form").style.display = "none";
  pendingSessionType = null;
});

document.getElementById("session-form-create-btn")?.addEventListener("click", () => {
  const uuid = document.getElementById("session-uuid-input")?.value?.trim();
  if (!uuid) { logWarn("MiniBrew UUID is required"); return; }
  let recipe = null;
  if (pendingSessionType === "brew") {
    const raw = document.getElementById("session-recipe-input")?.value?.trim();
    if (raw) { try { recipe = JSON.parse(raw); } catch { logWarn("Invalid recipe JSON — ignoring"); } }
  }
  const typeMap = { brew: 0, clean: "clean_minibrew", acid_clean: "acid_clean_minibrew" };
  createSession(typeMap[pendingSessionType], uuid, recipe);
  document.getElementById("session-form").style.display = "none";
  pendingSessionType = null;
});

document.getElementById("refresh-device-btn")?.addEventListener("click", () => { setActiveSource("overview"); refreshDeviceInfo(); });
document.getElementById("refresh-devices-btn")?.addEventListener("click", () => { setActiveSource("devices"); refreshDevices(); });

document.getElementById("auto-refresh-select")?.addEventListener("change", (e) => {
  const val = parseInt(e.target.value);
  if (val === 0) {
    stopAutoRefresh();
    log("Auto-refresh disabled");
  } else {
    startAutoRefresh(val);
  }
});

document.getElementById("clear-log-btn")?.addEventListener("click", () => {
  const el = document.getElementById("log-output");
  if (el) el.innerHTML = "";
  log("Log cleared");
});

document.getElementById("suppress-ws-logs")?.addEventListener("change", (e) => {
  suppressWsLogs = e.target.checked;
  log(`WebSocket logs ${suppressWsLogs ? "suppressed" : "shown"}`);
});

// Set default active source
document.getElementById("refresh-device-btn")?.classList.add("active");

let tokenGatePassed = false;

async function checkTokenAndGate() {
  try {
    const resp = await fetch("/settings/token");
    if (!resp.ok) throw new Error("Failed to fetch token status");
    const data = await resp.json();
    if (data.token_set) {
      tokenGatePassed = true;
      document.getElementById("token-gate").style.display = "none";
      connect();
    } else {
      document.getElementById("token-gate").style.display = "flex";
    }
  } catch (e) {
    document.getElementById("token-gate").style.display = "flex";
  }
}

async function loadTokenStatus() {
  try {
    const resp = await fetch("/settings/token");
    if (resp.ok) {
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
    if (srcEl) {
      srcEl.textContent = source === "env"
        ? "Source: .env file (default)"
        : source === "stored"
        ? "Source: encrypted storage"
        : "";
    }
  } else {
    el.innerHTML = '<span class="token-indicator token-indicator--unset">Not set</span>';
    if (srcEl) srcEl.textContent = "No token configured — enter one below to continue";
  }
}

function openSettingsModal() {
  document.getElementById("settings-modal").style.display = "flex";
  document.getElementById("settings-token-input").value = "";
  loadTokenStatus();
}

function closeSettingsModal() {
  document.getElementById("settings-modal").style.display = "none";
}

document.getElementById("settings-btn")?.addEventListener("click", openSettingsModal);
document.getElementById("settings-close-btn")?.addEventListener("click", closeSettingsModal);
document.getElementById("settings-overlay")?.addEventListener("click", closeSettingsModal);

document.getElementById("settings-save-btn")?.addEventListener("click", async () => {
  const token = document.getElementById("settings-token-input")?.value?.trim();
  if (!token) { logWarn("Token cannot be empty"); return; }
  const btn = document.getElementById("settings-save-btn");
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    const resp = await fetch("/settings/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const result = await resp.json();
    if (!resp.ok) { logError(`Save failed: ${result.error || resp.status}`); }
    else {
      logSuccess("Token saved and applied — reconnecting…");
      updateTokenStatusUI(true, "stored");
      closeSettingsModal();
      setTimeout(() => {
        if (ws) ws.close();
        connect();
      }, 500);
    }
  } catch (e) { logError(`Save error: ${e.message}`); }
  finally { btn.disabled = false; btn.textContent = "Save & Apply"; }
});

document.getElementById("settings-reset-btn")?.addEventListener("click", async () => {
  try {
    const resp = await fetch("/settings/token", { method: "DELETE" });
    if (resp.ok) {
      const data = await resp.json();
      logSuccess("Token reset — reconnecting…");
      updateTokenStatusUI(false, null);
      closeSettingsModal();
      setTimeout(() => {
        if (ws) ws.close();
        connect();
      }, 500);
    } else { logError("Reset failed"); }
  } catch (e) { logError(`Reset error: ${e.message}`); }
});

document.getElementById("settings-token-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("settings-save-btn")?.click();
  if (e.key === "Escape") closeSettingsModal();
});

document.getElementById("gate-submit-btn")?.addEventListener("click", async () => {
  const token = document.getElementById("gate-token-input")?.value?.trim();
  if (!token) {
    const err = document.getElementById("gate-error");
    err.textContent = "Token cannot be empty";
    err.style.display = "block";
    return;
  }
  const btn = document.getElementById("gate-submit-btn");
  const err = document.getElementById("gate-error");
  err.style.display = "none";
  btn.disabled = true;
  btn.textContent = "Connecting…";
  try {
    const resp = await fetch("/settings/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!resp.ok) {
      const result = await resp.json();
      err.textContent = result.error || "Failed to save token";
      err.style.display = "block";
    } else {
      err.style.display = "none";
      tokenGatePassed = true;
      document.getElementById("token-gate").style.display = "none";
      connect();
    }
  } catch (e) {
    err.textContent = `Error: ${e.message}`;
    err.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Connect";
  }
});

document.getElementById("gate-token-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("gate-submit-btn")?.click();
});

checkTokenAndGate();