# Gap Analysis — MiniBrew Session Orchestrator

Features, buttons, and UI elements that do not work as intended, grouped by dashboard section.

---

## 1. Authentication & Access Control

### 1.1 Login Form (`/auth/login`)
**Broken:** Any username/password combination is accepted. `auth_service.authenticate_user()` returns the hardcoded admin user regardless of input.
**Root cause:** `auth_service.py:63` — `authenticate_user()` ignores credentials in bypassed mode.
**Expected:** Real credential verification against a user database.
**Difficulty:** Medium — requires PostgreSQL users table + proper bcrypt password verification.

### 1.2 Register Form (`/auth/register`)
**Broken:** Registration always succeeds and returns `{"id": 1, "username": "<whatever>" }`. No user is actually persisted.
**Root cause:** `auth_service.py:66` — `create_user()` returns a fake user without writing to any database.
**Expected:** New user record created in PostgreSQL with a hashed password.
**Difficulty:** Medium — requires PostgreSQL + password hashing.

### 1.3 Logout Button (navbar `navbar-logout-btn`)
**Broken:** The button is rendered in `index.html:74` but is explicitly hidden in `app.js:154` (`logoutBtn.style.display = "none"`) during `initAuth()`.
**Root cause:** Bypassed auth means there is nothing to log out of, so the button is hidden to avoid confusing the user.
**Expected:** Visible logout button that clears JWT tokens and disconnects WebSocket.
**Difficulty:** Low — remove the hide line and wire `doLogout()` to it, but meaningful logout requires real auth first.

### 1.4 Settings → Logout / Relogin Button
**Broken:** Clicking "Logout / Relogin" in the settings modal (line 457) sets `tokenGatePassed = false` and shows the token gate. Since auth is bypassed and the MiniBrew token is independent, this is misleading — the user is shown the token gate again but nothing meaningful has changed.
**Root cause:** Auth gate is conflated with the token gate. There is no real auth session to terminate.
**Expected:** Proper separation of dashboard auth (JWT) and MiniBrew API token. Only JWT logout should show the auth gate.
**Difficulty:** Medium — requires real JWT auth before this action is meaningful.

### 1.5 All Protected `fetch()` Calls Missing Auth Headers
**Broken:** Several `fetch()` calls in `app.js` don't use `fetchWithAuth()` and therefore don't send a JWT:
- `sendCommand()` (line 981) — `fetch("/session/...")` instead of `fetchWithAuth()`
- `sendKegCommand()` (line 995) — `fetch("/keg/...")` instead of `fetchWithAuth()`
- `delete-session-btn` handler (line 1458) — `fetch("/sessions/...")`
- `detail-delete-btn` handler (line 1489) — `fetch("/sessions/...")`
- All three `session-form-create-btn` create calls (line 1458, 1481, 1489)

**Impact:** When JWT auth is enabled (real, not bypassed), these endpoints will return 401 because no Bearer token is sent.
**Root cause:** These endpoints were written when `get_current_user()` returned admin unconditionally.
**Difficulty:** Low — replace `fetch()` with `fetchWithAuth()` in each call site.

---

## 2. Settings Panel

### 2.1 Save & Apply Button (`POST /settings/token`)
**Broken:** The backend endpoint is protected by `Depends(require_current_user)`, but since auth is bypassed, anyone can overwrite the stored MiniBrew API token without actually being authenticated. This is a security issue if multi-user auth is ever enabled.
**Root cause:** Auth bypass on `require_current_user` means the user ID is always admin.
**Expected:** Only an authenticated user should be able to save a token.
**Difficulty:** Low — once real JWT auth is implemented, this is automatically secured.

### 2.2 Audit Log Viewer
**Broken:** The audit log correctly shows entries (since `audit_service.py` writes to JSONL), but `loadAuditLogs()` sends no filters and the backend `/audit/log` endpoint returns all entries newest-first — no pagination controls are wired in the UI despite `limit` and `offset` being settable in the request.
**Root cause:** The audit UI (settings modal) has only a "Load Recent Logs" button with no way to page through older entries or filter by user/action/result.
**Expected:** Pagination (prev/next), filter by action_type, filter by user_id.
**Difficulty:** Low — UI wiring only.

### 2.3 Audit Count Shows Only Loaded Entries
**Broken:** `settings-audit-count` (line 1132) shows `"${logs.length} of ${total} entries"` but `total` comes from the response which is the full count of all entries in the file, not the count matching any filters.
**Root cause:** `get_log_count()` in `audit_service.py` ignores all filter arguments.
**Expected:** `total` should reflect the count matching active filters.
**Difficulty:** Low — fix the SQL or filter logic in `audit_service.py`.

---

## 3. Base Station Controls (Brewery Status Tab)

### 3.1 END_SESSION Button (Duplicate — Two Buttons)
**Broken:** There are two "Delete Session" / "End Session" buttons in the controls grid:
- Line 166: `<button class="control-btn control-btn--danger" id="delete-session-btn" disabled>Delete Session</button>`
- Line 167: `<button class="control-btn" data-command="END_SESSION" disabled>End Session</button>`

`delete-session-btn` (line 1479) fires `wake-then-delete` directly. `END_SESSION` (line 1456) also fires `wake-then-delete` via its handler. They do the same thing, creating UI clutter and confusion.
**Expected:** Single "Delete Session" button.
**Difficulty:** Low — remove one button and consolidate the handler.

### 3.2 CHANGE_TEMPERATURE — `temp-input` Not Updated from Session State
**Broken:** When a session is selected, `updateCommandButtons()` shows the `temp-control` panel if `user_action` allows type 6, but the input field always shows the default value `70` (line 181: `value="70"`). It does not pre-fill from the session's current `serving_temperature` or `target_temp`.
**Expected:** Input pre-filled with current target temperature from the selected session.
**Difficulty:** Low — fetch and set the input value when loading session detail.

### 3.3 Auto-Refresh Creates Double-Polling
**Broken:** Two independent polling mechanisms run simultaneously:
1. `PollingWorker` in the backend pushes state via WebSocket every 2 seconds (always running)
2. `setAutoRefreshInterval()` in `app.js` ALSO polls `GET /verify` every N seconds (1/2/3/4/5/10s selectable in the UI)

The auto-refresh in the UI fetches `/verify` directly, overwriting `allDevices` and calling `updateDeviceUI()`, effectively duplicating what the WebSocket already provides — and only for the device panel, not for sessions or kegs.
**Root cause:** The 2s WebSocket push was not fully trusted; a manual polling fallback was added as a UX feature.
**Expected:** Remove the HTTP auto-refresh; rely entirely on WebSocket push. The browser auto-refresh dropdown should be removed or repurposed for something WebSocket can't provide (like a manual session list refresh).
**Difficulty:** Low — remove or disable the `setAutoRefreshInterval()` call on the device info panel.

### 3.4 BYPASS_USER_ACTION Command
**Broken:** `BYPASS_USER_ACTION` is sent as `command_type: 3` (generic) but the MiniBrew API may not treat it differently from `NEXT_STEP`. The command name implies the device should skip a user prompt, but the backend does not verify this is a valid bypass at the current `user_action`.
**Expected:** Backend should check `user_action` before dispatching `BYPASS_USER_ACTION`, similar to how `FINISH_BREW_FAILURE` maps to specific failure states.
**Difficulty:** Low — add `BYPASS_USER_ACTION` to the command type map with appropriate guard conditions.

### 3.5 GO_TO_MASH / GO_TO_BOIL
**Broken:** These commands are gated in `CMD_DEFINITIONS` to specific user_action ranges, but the backend guard in `ALLOWED_COMMANDS_BY_USER_ACTION` only maps user_action to generic allowed command types — it does not distinguish between `GO_TO_MASH` and `NEXT_STEP`. Both are `type: 3`.
**Expected:** If `GO_TO_MASH` is allowed at a given user_action, the device should jump to mash phase (not just advance one step). The MiniBrew API may not support this as a distinct command — needs verification against the API spec.
**Difficulty:** Unknown — requires MiniBrew API verification to confirm whether these are distinct commands or aliases for `NEXT_STEP`.

### 3.6 FINISH_BREW_SUCCESS / FINISH_BREW_FAILURE
**Broken:** `CMD_DEFINITIONS` gates `FINISH_BREW_SUCCESS` to `allowedUA: [30]` (Fermentation complete) and `FINISH_BREW_FAILURE` to `allowedUA: [71, 84]` (failure states). But these commands may not be valid API commands — the MiniBrew API may not accept them at all.
**Expected:** Commands actually succeed when invoked.
**Difficulty:** Unknown — requires MiniBrew API verification.

---

## 4. Kegs

### 4.1 Associate Keg Button
**Broken:** Clicking "Associate Keg" (`associate-keg-btn`, line 177) calls `POST /sessions/${currentSessionId}/associate-keg`. This endpoint **does not exist on the backend** — there is no route for `associate-keg` in `main.py`. It always returns a 404.
**Root cause:** The button was implemented in the frontend without a corresponding backend endpoint.
**Expected:** Either implement the backend endpoint (MiniBrew may or may not support keg-session association) or remove the button.
**Difficulty:** Medium — requires backend endpoint + MiniBrew API research.

### 4.2 Set Beer Name — No Success/Error Feedback
**Broken:** `set-beer-name-btn` (line 1530) calls `POST /keg/{uuid}/display-name`. If the API call fails (e.g., the keg UUID is wrong), the error is caught and logged, but the user sees no visual feedback in the UI.
**Expected:** Toast notification or inline error/success message in the keg section.
**Difficulty:** Low — add `logSuccess`/`logError` wrapper around the response.

### 4.3 Keg Temperature — No Validation
**Broken:** `keg-temp-input` (line 206) accepts any value from 0 to 30 with step 0.1. No validation against realistic serving temperatures (e.g., 0–15°C typical) or against the keg's current mode.
**Expected:** Validation or guard that warns if temperature is out of a valid range.
**Difficulty:** Low — add frontend validation before calling `sendKegCommand`.

---

## 5. Sessions

### 5.1 Session Form — Recipe ID is Not Actually Used
**Broken:** The "Recipe ID (optional)" field in the session creation form (line 236) passes a recipe ID integer to `createSessionFn()`, which sends it in `beer_recipe`. However, `session_service.py:56` uses `beer_recipe or {}` — if the value is a raw integer ID (not a structured JSON blob), it may not be correctly interpreted by `POST /v1/sessions/`.
**Expected:** If a recipe ID is provided, either fetch the full recipe and pass it as the `beer_recipe` blob, or confirm the API accepts a bare recipe ID.
**Difficulty:** Medium — requires MiniBrew API verification of the `beer_recipe` field format.

### 5.2 Session Status Filtering
**Broken:** The sessions dropdown shows ALL sessions — active, completed (status 4), failed (status 6) — sorted by ID descending. There is no way to filter to only active sessions.
**Expected:** Active/In-Progress/All toggle in the sessions section.
**Difficulty:** Low — add a status filter dropdown and filter `sessionsData` before rendering.

### 5.3 Session Detail — Delete Button Has No Auth Headers
**Broken:** `detail-delete-btn` handler (line 1487) uses raw `fetch()` without `fetchWithAuth()`, meaning it will fail with 401 when proper JWT auth is enabled.
**See:** Issue 1.5 (same fix applies).
**Difficulty:** Low — swap `fetch()` for `fetchWithAuth()`.

### 5.4 Session Detail — Process State Shows `NULL` for Unknown States
**Broken:** If the MiniBrew API returns a `process_state` code not in `PROCESS_STATE_MAP`, it renders as `X (NULL)` in red. However, many observed states (5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 39, 43, 52, 59, 74, 76, 77, 78, 81, 82, 83, 111, 112, 113, 114) are in `PROCESS_STATE_MAP` but NOT in the frontend's `PROCESS_STATE_MAP` in `app.js`. The frontend code table is missing many states that the backend `state_engine.py` knows about.
**Expected:** Frontend `PROCESS_STATE_MAP` in `app.js` should be in sync with `state_engine.py`.
**Difficulty:** Low — copy the state map from `state_engine.py` into `app.js`.

### 5.5 Session Form — Pre-filled UUID Not Auto-Selected After Creation
**Broken:** After creating a session, `currentSessionId` is set (line 854: `currentSessionId = String(sid)`) but the device selector dropdown (`device-select`) is not updated to reflect the device used for the new session.
**Expected:** Device UUID pre-fill in the form should persist or the device list should be refreshed after session creation.
**Difficulty:** Low — minor UX fix.

---

## 6. Recipes

### 6.1 Import Recipe — No Backend Endpoint
**Broken:** `handleRecipeImport()` (line 1286) calls `POST /recipes/` to create a new recipe via `fetchWithAuth("/recipes", {method: "POST", ...})`. The backend `recipe_service.py:40` has `create_recipe()` which calls `MiniBrewClient.create_recipe()`, which calls `POST /recipes/`. However, `main.py` has **no route** for `POST /recipes/`. There is only `GET /recipes/{id}` and `GET /recipes/{id}/steps`. The import will return a 404 or API error.
**Expected:** Either implement `POST /recipes` on the backend (MiniBrew API must support it) or remove the import button.
**Difficulty:** Medium — requires backend route + MiniBrew API research.

### 6.2 Recipe Notes — Not Persisted
**Broken:** Public notes and private notes textareas (lines 312–315) are only stored in the DOM textarea elements. Export JSON includes them (lines 1262–1263), but they are never sent to or stored on any backend. Refreshing the page clears them.
**Expected:** Notes persisted to PostgreSQL (future) linked to the recipe + user.
**Difficulty:** Medium — requires database schema and backend endpoint (future feature).

### 6.3 Recipe Notes — Public/Private Separation is Arbitrary
**Broken:** Both notes textareas are stored in the same `exportData` object under `public_notes` and `private_notes`. The backend/recipe API has no concept of this distinction — the MiniBrew API may or may not support custom fields.
**Expected:** Confirm whether the MiniBrew API accepts these fields; if not, document that they are local-only.
**Difficulty:** Low — document the limitation.

### 6.4 Load Recipes — `.error` Check Never Fires
**Broken:** `loadRecipes()` (line 682) checks `if (data.error)` to detect errors. But `GET /recipes` returns `{"recipes": [...]}`, not `{"error": "..."}`. Errors from the API would be a different format. Success responses have no `.error` field, so this check is a no-op.
**Expected:** Proper error detection from HTTP status codes, not from response body shape.
**Difficulty:** Low — check `resp.ok` and HTTP status instead of `data.error`.

### 6.5 Start Brew from Recipe — Wrong Payload Format
**Broken:** `startBrewFromRecipe()` (line 848) sends `{ session_type: 0, minibrew_uuid: uuid, beer_recipe: recipeId }` where `recipeId` is a string from `card.dataset.id`. The backend `session_service.py:56` uses `beer_recipe or {}` — passing a bare ID string may not be what the MiniBrew API expects for a brew session recipe reference.
**Expected:** Either fetch the full recipe detail and pass the full recipe object, or confirm the API accepts a recipe ID integer.
**Difficulty:** Medium — requires MiniBrew API verification.

---

## 7. Water Profiles

### 7.1 Water Profiles Tab Not Loaded Automatically
**Broken:** The Water Profiles tab content is loaded from `7L_water_profiles.json` via `loadWaterProfiles()` on page load (line 1724). However, if the JSON file fails to load, the tab shows an error. There is no retry logic and no visual indication that the data loaded successfully until the user clicks the tab.
**Expected:** Lazy-load water profiles when the tab is first clicked; show a loading indicator; cache in memory.
**Difficulty:** Low — move `loadWaterProfiles()` to be triggered on first tab activation rather than on page load.

### 7.2 Copy to Brew Notes — Clipboard API May Fail Silently
**Broken:** `copyWaterToNotes()` (line 1396) uses `navigator.clipboard.writeText()`. On browsers where the Clipboard API is not available (some headless or restricted environments), it silently catches the error and shows "Copy failed" for 2 seconds — but does not fall back to selecting the text or copying via a different mechanism.
**Expected:** Fallback: select the text in a temporary `<textarea>` and use execCommand copy.
**Difficulty:** Low — add a fallback copy mechanism.

---

## 8. Nginx Proxy

### 8.1 Missing Proxy Routes for Recipe Sub-Path
**Broken:** `nginx.conf` has a route for `/recipes` but NOT for `/recipes/` (with trailing slash). The frontend may or may not use a trailing slash. Similarly, `/recipe` (singular, no trailing slash) maps to `http://backend:8000/recipe` — but there is no singular recipe route on the backend.
**Expected:** Consistent trailing-slash handling; remove or correct the singular `/recipe` proxy route.
**Difficulty:** Low — audit and fix nginx route configuration.

### 8.2 `/users` Proxy Route
**Broken:** `nginx.conf:60` proxies `/users` to `http://backend:8000/users` but there is no `/users` endpoint on the backend. The frontend calls `/users/me` via `fetchWithAuth("/users/me")` (line 156), but the nginx route for `/users` would proxy to a non-existent backend endpoint.
**Expected:** Remove the `/users` proxy route or replace with the actual backend endpoint path.
**Difficulty:** Low — remove dead nginx route.

---

## 9. Critical Broken Items (No Backend Endpoint)

| Frontend Element | Endpoint Called | Backend Status |
|-----------------|-----------------|---------------|
| Associate Keg button | `POST /sessions/{id}/associate-keg` | **404 — endpoint does not exist** |
| Import Recipe button | `POST /recipes/` | **404 — endpoint not routed in main.py** |
| `/users/me` | `GET /users/me` | **404 — no such route on backend** |

---

## Difficulty Legend

| Level | Meaning |
|--------|---------|
| **Low** | UI fix, frontend-only change, or straightforward 1-line backend fix |
| **Medium** | Requires API research, new database table, or moderate refactoring |
| **Unknown** | Requires MiniBrew API specification verification before a fix can be planned |
