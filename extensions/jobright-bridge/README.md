# Resume Agent ↔ Jobright Bridge Extension

Chrome/Edge extension (one folder): Jobright entry **and** ATS form-fill co-pilot.

## Install (Load unpacked)

1. Start backend (`:8000`) and frontend (`:3000`).
2. Chrome → `chrome://extensions` → Developer mode → **Load unpacked**.
3. Select this folder only: `extensions/jobright-bridge`.
4. After code updates: click **Reload** on the extension card.

## What it does

### A) Jobright → Resume Agent
- Open a Jobright job detail **or** local mock: `http://localhost:3000/fixtures/jobright-mock.html`
- Green **Open Tailor** FAB on the page, **or** toolbar popup → **Open Tailor**
- Imports JD and opens Tailor / Apply / Outreach in a full window

### B) Auto apply (form-fill)
- Toolbar popup → paste **Apply URL** → **打开并填表**
- Opens the ATS tab, calls Decision Engine (`POST /engine/step`), fills fields
- Always **paused_before_submit** — never auto-clicks Submit

Default token: `dev-extension-token` (matches backend `EXTENSION_BRIDGE_TOKEN`).

## Note

Older docs pointed at `entrypoints/jobright_extension/`. That code now lives **here**. Use this directory only.
